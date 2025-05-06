import os
import re
import sys
import json
import time
import shutil   
import tiktoken
import pprint
import subprocess
import ast
import textwrap
import argparse
import inspect
import traceback
import signal
from datetime import datetime
from pathlib import Path
# from datasets import load_dataset
from swe_log import init_logger, log_msg, log_and_print, remove_ansi_escape_sequences
from model import LLMModel
from retrieve_src import retrieve_code_element, retrieve_code_element_in_database
from run_report import get_eval_report_for_log
from constants import MAP_VERSION_TO_INSTALL
from utils import get_test_directives, execute_command, backup_repo, restore_repo, count_lines, update_history
from format import extract_json_instruction, extract_trace_reply, extract_function_call, \
    extract_filter_reply, extract_review_reply, judge_review_reply, judge_ready_generation
from prompt import GEN_DEBUGGING_TEST, DEBUGGING_AGENT_SYSTEM_MSG, \
    ANALYSE_TEST, MODIFY_SOURCE_CODE_HEAD, MODIFY_SOURCE_CODE_INSTRUCT, TOO_LONG_EXEC_RESULT, \
    DEBUGGING_START_AFTER_TESTING, CHOOSE_SCOPE_INSTRUCT, CHOOSE_METHOD_INSTRUCT, BEGIN_INTRO, \
    DEBUGGING_CHOOSE_SCOPE, DEBUGGING_CHOOSE_METHOD, REPAIR_COLLECT_HEAD, COLLECT_INSTRUCT, \
    REPAIR_INSTRUCT, FILTER_INSTRUCT, REVIEW_PATCH_INSTRUCT, REGENERATION_INSTRUCT

# sys.path.append(os.path.abspath('/data/swe-fl/SRC/SWE-Bench-Validation/src'))


MODEL_NAME = 'gpt-4o'
# MODEL_NAME = 'qwen2.5:32b-instruct-fp8'
# MODEL_NAME = 'gpt-4o-2024-05-13'
# MODEL_NAME = 'gpt-4o-2024-08-06'
# MODEL_NAME = 'o1-mini-2024-09-12'
# MODEL_NAME = 'claude-3-5-sonnet-20241022'

TESTBED_DIR = Path("/data/swe-fl/TMP/testbed/")
DBGSNOOPER_DIR = Path("/data/swe-fl/SRC/pysnooper_axel/dbgsnooper")
CHECKOUT_REPO_DIR = Path("/data/swe-fl/EXP/swe-evaluation/swe-verified-checkout/gold")

EXP_DIR = "/data/swe-fl/SRC/DebuggingAgent/log"

# os.environ['HF_DATASETS_CACHE'] = '~/.cache/huggingface/datasets/'

CONDA_ACTIVATE_PATH = 'source /root/miniforge3/bin/activate'


remove_timestamps = lambda s: re.sub(
    r'(Elapsed time:\s*\d{2}:\d{2}:\d{2}\.\d+|\b\d{2}:\d{2}:\d{2}\.\d+\b)(?:\r?\n)?',
    '',
    s
)

    

def filter_and_choose_code_element(instance: dict, agent: LLMModel, retrieve_round_output: str, api_reply_dict):
    key = list(api_reply_dict.keys())[0]
    if len(api_reply_dict[key]) == 1:
        return api_reply_dict[key]
    
    filtered_result = []
    search_api_results = build_api_call_reply_promopt(api_reply_dict)
    filter_prompt = FILTER_INSTRUCT.format(
        project=instance['repo'].split('/')[1],
        issue=instance['problem_statement'],
        retrieve_round_output = retrieve_round_output,
        search_api_results = search_api_results
        )
    response = query_model_with_retry(agent, filter_prompt, extract_filter_reply, instance)
    extracted_reply = extract_filter_reply(response)
    
    if api_reply_dict[key][0]['type'] == 'code_snippet':
        for item in extracted_reply:
            for api_result in api_reply_dict[key]:
                if api_result['path'] == item['file_path'] and api_result['start_line'] == item['start_line'] and api_result['end_line'] == item['end_line']:
                    filtered_result.append(api_result)
    
    else:
        for item in extracted_reply:
            for api_result in api_reply_dict[key]:
                if api_result['path'] == item['file_path'] and api_result['name'] == item['name']:
                    filtered_result.append(api_result)
    
    if len(filtered_result) == 0:
        raise ValueError("No valid filter reply results found.")
    return filtered_result
                        

def init_instance_testbed(instance: dict):
    # Setup testbed for target instance
    TESTBED_DIR.mkdir(parents=True, exist_ok=True)
    
    subdire = None
    for dire in os.listdir(CHECKOUT_REPO_DIR / instance['instance_id']):
        if os.path.isdir(CHECKOUT_REPO_DIR / instance['instance_id'] / dire):
            subdire = dire
    raw_repo_path = CHECKOUT_REPO_DIR / instance['instance_id'] / subdire
    testbed_path = TESTBED_DIR / instance['instance_id']

    try:
        if not raw_repo_path.exists():
            raise FileNotFoundError(f"Source directory does not exist: {raw_repo_path}")
        
        if testbed_path.exists():
            shutil.rmtree(testbed_path)
            log_msg(f"Remove exist testbed_path: {testbed_path}")
        
        shutil.copytree(raw_repo_path, testbed_path, symlinks=True)

    except Exception as e:
        log_msg(f"Error copying repository: {e}")
        raise


    # Reinstall conda environment
    install_snooper_cmd = f'python -m pip install -e .'
    
    setup_repo_env_cmd = f"cd {instance['testbed_src_path']} && {CONDA_ACTIVATE_PATH} {instance['conda_env_name']} \
           && cd {DBGSNOOPER_DIR} && {install_snooper_cmd} && cd {instance['testbed_src_path']}\
           && {instance['conda_env_install_cmd']} && echo SUCCESS"

    log_and_print(f"Setup testbed environment: {instance['instance_id']}")
    
    std_out, std_err = execute_command(setup_repo_env_cmd, 600, verbose=True)

    if 'SUCCESS' in std_out:
        log_msg('Setup testbed: Done')
    else:
        log_msg(std_out)
        log_msg(std_err)


def load_instance_data(instance_id: str):
    # dataset = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")  
    # instance_index = dataset['instance_id'].index(instance_id)  
    # instance = {}

    # for attr in dataset[instance_index].keys():
    #     instance[attr] = dataset[attr][instance_index]
    SWE_TASK_PATH = '/data/swe-fl/DATA/swe-bench-new.json'
    with open(SWE_TASK_PATH, 'r') as f:
        dataset = json.load(f)
    for item in dataset:
        if item['instance_id'] == instance_id:
            instance = item
            break

    instance['conda_env_name'] = '-'.join(instance_id.split('-')[:-1]) + '__' + instance['version']

    owner_proj_name = ('-'.join(instance_id.split('-')[:-1])).replace('__', '/')
    
    instance['conda_env_install_cmd'] = MAP_VERSION_TO_INSTALL[owner_proj_name][instance['version']]['install']

    # log_and_print(instance['problem_statement'])
    
    log_and_print(instance['FAIL_TO_PASS'])

    log_and_print(instance['conda_env_install_cmd'])

    test_type = MAP_VERSION_TO_INSTALL[owner_proj_name][instance['version']]['test_cmd']
    test_directives = get_test_directives(instance)
    
    instance['test_cmd'] = f"{test_type} {' '.join(test_directives)}"
    log_and_print(instance['test_cmd'])

    # instance['testbed_src_path'] = TESTBED_DIR / instance['instance_id'] / instance['conda_env_name']
    instance['testbed_src_path'] = TESTBED_DIR / instance['instance_id']

    log_and_print(str(instance['testbed_src_path']))
    
    return instance


def exec_debugging_test(instance: dict, file_scope_dict=None, depth=2, loop=None) -> str:
    test_path = os.path.join(instance['testbed_src_path'], 'reproduce.py')
    if depth == -1:
        exec_test_out, exec_test_err = execute_command(f"cd {instance['testbed_src_path']} && \
                                {CONDA_ACTIVATE_PATH} {instance['conda_env_name']} && python {test_path}", 300, verbose=True)
        return exec_test_out + exec_test_err
    # if file_scope_dict is None (Step 1), then just observe the whole test file
    file_scope_dict = file_scope_dict or {str(test_path): (0, count_lines(test_path))}
    new_file_scope_dict = {}
    for file_path in file_scope_dict:
        if not os.path.exists(file_path):
            abs_file_path = os.path.join(instance['testbed_src_path'], file_path)
        else:
            abs_file_path = os.path.abspath(file_path)
        new_file_scope_dict[abs_file_path] = file_scope_dict[file_path]
    file_scope_dict = new_file_scope_dict
    
    dict_json = json.dumps(file_scope_dict)
    
    cmd = [
        "conda", "run", "-n", instance['conda_env_name'],
        "python", "run_debugging_test.py",
        "--test-path", test_path,
        "--file-scope-dict", dict_json
    ]
    
    cmd += ["--depth", str(depth)]
    
    if loop is not None:
        cmd += ["--loop", str(loop)]
    
    # stdout, stderr = execute_command(' '.join(cmd), 300, verbose=False)
    result = subprocess.run(cmd, capture_output=True, text=True)

    result_clean = remove_timestamps(
        remove_ansi_escape_sequences(result.stdout + result.stderr)
        )

    lines = [
        line for line in result_clean.splitlines()
        if "SOURCE IS UNAVAILABLE" not in line
    ]
    total_lines = len(lines)
    
    if total_lines > 500:
        truncated_output = '\n'.join(lines[:500]) + '\n' + TOO_LONG_EXEC_RESULT
        return truncated_output
    else:
        return '\n'.join(lines)  


def analyse_debugging_test(instance: dict, debugging_agent: LLMModel, debugging_test_exec_result):
    start_debugging_prompt = ANALYSE_TEST.format(
        debugging_test_exec_result = debugging_test_exec_result
    )

    log_and_print('start_debugging')

    start_debugging_response = query_model_with_retry(debugging_agent, start_debugging_prompt, extract_json_instruction, instance)

    start_debugging_instruction = extract_json_instruction(start_debugging_response)

    if not start_debugging_instruction['is_debugging_test_successfully_generated']:
        raise ValueError("Debugging test was not successfully generated.")
    
    #TODO the regenerate process 
    start_debugging_instruction['move_to_step_3'] = False

    return start_debugging_instruction


def get_element_from_name(instance: dict, file_name: str, element_name: str, element_type: str, enable_line_number: bool = False, relative_path: bool = True):
    if not os.path.exists(file_name):
        abs_file_path = os.path.join(instance['testbed_src_path'], file_name)
    else:
        abs_file_path = os.path.abspath(file_name)
    retrieve_result = retrieve_code_element(abs_file_path, element_name, element_type, enable_line_number, relative_path, instance)
    return retrieve_result


def judge_method_choose(response: str, instance) -> bool:
    try:
        trace_reply = extract_trace_reply(response)
        if trace_reply['type'].lower() == 'buggy method' or trace_reply['type'].lower() == 'observed method':
            file_name = trace_reply['file']
            if not os.path.exists(file_name):
                abs_file_path = os.path.join(instance['testbed_src_path'], file_name)
            else:
                abs_file_path = os.path.abspath(file_name)
            if os.path.exists(abs_file_path):
                retrieve_result = retrieve_code_element(abs_file_path, trace_reply['method'], 'method')
            else:
                raise Exception(f'File {file_name} not found')
        else:
            raise Exception(f'Expected buggy method or observed method but got {trace_reply["type"]}')
    except Exception as e:
        raise Exception(f'Exception occurs when method choosing: {e}')

    return True


def judge_scope_or_method_choose(response: str, instance) -> bool:
    try:
        trace_reply = extract_trace_reply(response)
        if trace_reply['type'].lower() == 'observed scope':
            file_name = trace_reply['file']
            if not os.path.exists(file_name):
                abs_file_path = os.path.join(instance['testbed_src_path'], file_name)
            else:
                abs_file_path = os.path.abspath(file_name)
            if os.path.exists(abs_file_path):
                observed_start_line = trace_reply['start_line']
                observed_end_line = trace_reply['end_line']
                retrieve_result = retrieve_code_element(abs_file_path, f'{observed_start_line}-{observed_end_line}','scope')[0]
            else:
                raise Exception(f'File {file_name} not found')
        
        elif trace_reply['type'].lower() == 'buggy method':
            file_name = trace_reply['file']
            if not os.path.exists(file_name):
                abs_file_path = os.path.join(instance['testbed_src_path'], file_name)
            else:
                abs_file_path = os.path.abspath(file_name)
            if os.path.exists(abs_file_path):
                retrieve_result = retrieve_code_element(abs_file_path, trace_reply['method'], 'method')
            else:
                raise Exception(f'File {file_name} not found')
        elif trace_reply['type'].lower() == 'observed method':
            file_name = trace_reply['file']
            if not os.path.exists(file_name):
                abs_file_path = os.path.join(instance['testbed_src_path'], file_name)
            else:
                abs_file_path = os.path.abspath(file_name)
            if os.path.exists(abs_file_path):
                retrieve_result = retrieve_code_element(abs_file_path, trace_reply['method'], 'method')
            else:
                raise Exception(f'File {file_name} not found')
            
        else:
            raise Exception(f'Expected observed scope or buggy method but got {trace_reply["type"]}')
                
    except Exception as e:
        raise Exception(f'Exception occurs when scope choosing: {e}')

    return True
    

def judge_api_call(response: str, instance: dict, agent: LLMModel):
    function_calls = extract_function_call(response)
    if len(function_calls) > 0:
        results = {}
        for function_call in function_calls:
            try:
                api_response = function_invoke(response, function_call, instance, agent, judge=True)
                if len(api_response)>0:
                    results[function_call['source_line']] = api_response
            except:
                continue
        if len(results) == 0:
            raise ValueError("No valid API call result.")
        return results
    elif judge_ready_generation(response):
        return 'ready'
    else:
        raise ValueError("No API call or Ready Generation Signal found in the response.")


def process_api_call(response: str, instance: dict, agent: LLMModel):
    function_calls = extract_function_call(response)
    if len(function_calls) > 0:
        results = {}
        for function_call in function_calls:
            try:
                api_response = function_invoke(response, function_call, instance, agent)
                if len(api_response)>0:
                    results[function_call['source_line']] = api_response
            except Exception as e:
                source_line = function_call['source_line']
                traceback.print_exc()
                log_and_print(f"Error occurred when invoking function call: {source_line}. Error: {str(e)}")
                
        if len(results) == 0:
            raise ValueError("No valid API call result.")
        return results
    elif judge_ready_generation(response):
        return 'ready'
    else:
        raise ValueError("No API call or Ready Generation Signal found in the response.")


def build_api_call_reply_promopt(api_call_results) -> str:
    prompt = 'Your API invoke result:\n'
    for api_call_result in api_call_results:
        prompt+= f'\n### API INVOKE: {api_call_result}\nRESULT:\n'
        for retrieve_info in api_call_results[api_call_result]:
            file_path = retrieve_info['path']
            element_name = retrieve_info['name']
            if retrieve_info['type'] != 'code_snippet':
                prompt += f'#### {file_path}:{element_name}\n'
            else:
                start_line = retrieve_info['start_line']
                end_line = retrieve_info['end_line']
                prompt += f'#### {file_path}:{start_line}-{end_line}\n'
            retrieve_code = retrieve_info['code']
            prompt += f'```python\n{retrieve_code}\n```\n\n'
            
    return prompt
        
        
def save_chat(instance: dict, prompt: str, response: str):
    detailed_chat_dir = Path(f"{EXP_DIR}/{instance['instance_id']}/chat")
    if not detailed_chat_dir.exists():
        detailed_chat_dir.mkdir(parents=True)
    cur_index = 0
    for file in os.listdir(detailed_chat_dir):
        file_index = int(file.split("_")[0])
        if file_index > cur_index:
            cur_index = file_index
    with open(detailed_chat_dir / f"{cur_index + 1}_input.txt", "w") as f:
        f.write(prompt + "\n")
    with open(detailed_chat_dir / f"{cur_index + 1}_output.txt", "w") as f:
        f.write(response + "\n")


def query_model_with_retry(model: LLMModel, prompt: str, judge_function, instance, max_retries: int = 5, retry_msg: str = None):
    success = False
    retries = 0
    response = ''
    while retries < max_retries:
        retries += 1
        try:
            response = model.query_model(prompt)
            save_chat(instance, prompt, response)
            if len(inspect.signature(judge_function).parameters) == 1:
                if judge_function(response):
                    success = True
                    break
            elif len(inspect.signature(judge_function).parameters) == 2:
                if judge_function(response, instance):
                    success = True
                    break
            elif len(inspect.signature(judge_function).parameters) == 3:
                if judge_function(response, instance, model):
                    success = True
                    break
            else:
                raise ValueError("judge_function should have 1, 2 or 3 parameters.")
            raise Exception('Judge function failed.')
        except Exception as e:
            if retry_msg:
                log_and_print(retry_msg)
            log_and_print(f"Error occurred when querying model.\n{str(e)}\nRetrying..({retries}/{max_retries})")
                
    if not success:
        log_and_print("Failed to get valid model response after multiple attempts.")
        raise ValueError("Failed to get valid model response after multiple attempts.")
    
    return response


def choose_method_with_feedback_retry(instance: dict, model: LLMModel, prompt: str, max_retries: int = 4):
    success = False
    retries = 0
    response = ''
    while retries < max_retries:
        retries += 1
        try:
            response = model.query_model(prompt)
            save_chat(instance, prompt, response)
            if judge_method_choose(response, instance):
                success = True
                break
        except Exception as e:
            prompt += '\n' + '=' * 50 + '## Your output:\n' + response + '=' * 50 + '\n\n## API Return result:\n' + str(e) +'\n\n\nPlease retry.'

    if success:
        return response
    else:
        raise ValueError(f'Failed to get valid Method Choose response after multiple attempts')


def deep_dive_debugging(instance: dict, debugging_agent: LLMModel, debugging_test_exec_result: str, reproduce_test_code: str):

    debugging_agent.clear_memory()
    initial_debugging_prompt = DEBUGGING_START_AFTER_TESTING.format(
        project=instance['repo'].split('/')[1],
        issue=instance['problem_statement'],
        test_code = reproduce_test_code,
        terminal_output = debugging_test_exec_result
    ) + CHOOSE_METHOD_INSTRUCT
    model_response = query_model_with_retry(debugging_agent, initial_debugging_prompt, judge_method_choose, instance)
    # model_response = choose_method_with_feedback_retry(instance, debugging_agent, initial_debugging_prompt)
    history = '\n' + '='*50 + '\n' + model_response + '\n' + '='*50 + '\n'
    debugging_depth = 1
    begin_prompt = BEGIN_INTRO.format(
        project = instance['repo'].split('/')[1],
        issue = instance['problem_statement'],
        test_code = reproduce_test_code
    )
    
    while debugging_depth < 5:
        log_and_print(f'deep_dive_debugging depth: {debugging_depth}')
        trace_reply = extract_trace_reply(model_response)
        if trace_reply['type'].lower() == 'buggy method':
            log_and_print(f'choose buggy method: {trace_reply["file"]}:{trace_reply["method"]}')
            return trace_reply['file'], trace_reply['method'], history
        else:
            observed_method = trace_reply['method']
            observed_file = trace_reply['file']
        observed_method_info = get_element_from_name(instance, observed_file, observed_method, element_type = 'method', enable_line_number = True)[0]
        observed_file = str(observed_method_info['path'])
        observed_method_code = observed_method_info['code']
        file_line_dict = {observed_file: (observed_method_info['start_line'], observed_method_info['end_line'])}
        observed_method = observed_method_info['name']
        
        log_and_print(f'choose method: {observed_file}:{observed_method}')
        ## chose scope
        test_exec_result = exec_debugging_test(instance, file_line_dict, depth = 1)
        
        choose_scope_prompt = begin_prompt + DEBUGGING_CHOOSE_SCOPE.format(
            history = history,
            observe_method = observed_method,
            method_code = observed_method_code,
            runtime_info = test_exec_result
        ) + CHOOSE_SCOPE_INSTRUCT
        model_response = query_model_with_retry(debugging_agent, choose_scope_prompt, judge_scope_or_method_choose, instance)
        history = update_history(history, model_response)
        trace_reply = extract_trace_reply(model_response)
        
        if trace_reply['type'].lower() == 'buggy method':
            log_and_print(f'choose buggy method: {trace_reply["file"]}:{trace_reply["method"]}')
            return trace_reply['file'], trace_reply['method'], history
        
        elif trace_reply['type'].lower() == 'observed method':
            debugging_depth += 1
            continue
        
        ## chose method
        observed_file = trace_reply['file']
        observed_start_line = trace_reply['start_line']
        observed_end_line = trace_reply['end_line']
        
        log_and_print(f'choose scope: {observed_file}:{observed_start_line}-{observed_end_line}')
        
        method_info = get_element_from_name(instance, observed_file, f'{observed_start_line}-{observed_end_line}', 'scope', True)[0]
        code_snippet = method_info['code']
        observed_file = str(method_info['path'])
        file_line_dict = {observed_file: (observed_start_line, observed_end_line)}
        test_exec_result = exec_debugging_test(instance, file_line_dict, depth = 2)
        choose_method_prompt = begin_prompt + DEBUGGING_CHOOSE_METHOD.format(
            history = history,
            observe_method = observed_method,
            code_snippet = code_snippet,
            runtime_info = test_exec_result
        ) + CHOOSE_METHOD_INSTRUCT
        model_response = query_model_with_retry(debugging_agent, choose_method_prompt, judge_method_choose, instance)
        # model_response = choose_method_with_feedback_retry(instance, debugging_agent, choose_method_prompt)
        history = update_history(history, model_response)
        debugging_depth += 1
        
    return None, None, None


def apply_patch(instance: dict, debugging_instruction: dict):
    """
    Apply code modifications to the source files using search/replace blocks.
    
    Args:
        instance (dict): Contains testbed source path information
        debugging_instruction (dict): Contains search/replace edit blocks
    
    The `debugging_instruction` dictionary structure:
    {
        "search_replace_edits": [
            "### file_path\n<<<<<<< SEARCH\n...\n=======\n...\n>>>>>>> REPLACE",
            ...
        ]
    }
    """
    edits = debugging_instruction.get("search_replace_edits", [])
    if not edits:
        raise ValueError("No dictionary key named 'search_replace_edits' found in debugging_instruction.")

    # Group edits by file path
    file_edits = {}
    for edit in edits:
        try:
            lines = edit.split('\n')
            file_path = lines[0].replace('### ', '')
            file_path = file_path.strip()
            if file_path not in file_edits:
                file_edits[file_path] = []
            
            # Extract SEARCH and REPLACE blocks
            search_idx = lines.index("<<<<<<< SEARCH") + 1
            replace_idx = lines.index("=======")
            end_idx = lines.index(">>>>>>> REPLACE")
            
            search_block = '\n'.join(lines[search_idx:replace_idx])
            replace_block = '\n'.join(lines[replace_idx+1:end_idx])
            
            file_edits[file_path].append((search_block, replace_block))
            
        except (ValueError, IndexError) as e:
            log_msg(f"Invalid edit format: {str(e)}")
            raise ValueError("Malformed search/replace edit block. Are you sure the format follows the example of a *SEARCH/REPLACE* edit correctly?") from e

    with open(f'{EXP_DIR}/{instance["instance_id"]}/{instance["instance_id"]}_edits.log', 'w') as f:
        f.write('\n'.join(edits))
    
    
    modified_files = set()
    # Process each file
    try:
        for file_path, edits in file_edits.items():
            if not os.path.exists(file_path):
                abs_path = instance['testbed_src_path'] / file_path
            else:
                abs_path = Path(file_path)
            if not abs_path.exists():
                log_msg(f"File not found: {abs_path}")
                raise FileNotFoundError(f"File not found: {abs_path}")

            # Read original content
            with open(abs_path, 'r') as f:
                content = f.read()

            # Apply edits sequentially
            modified = content
            for search, replace in edits:
                # if search in modified:
                #     modified = modified.replace(search, replace)  # Replace all occurrence
                #     continue
                # Normalize and strip for matching
                modified_lines = modified.split('\n')
                modified_stripped_lines = [line.strip() for line in modified_lines]
                modified_normalized = '\n'.join(modified_stripped_lines)

                search_lines = search.split('\n')
                search_stripped_lines = [line.strip() for line in search_lines]
                search_normalized = '\n'.join(search_stripped_lines)

                if search_normalized in modified_normalized:
                    for i in range(len(modified_lines) - len(search_lines), -1, -1):  # 从下往上遍历
                        window = modified_lines[i:i+len(search_lines)]
                        window_stripped = [line.strip() for line in window]
                        if '\n'.join(window_stripped) == search_normalized:
                            # 计算最小缩进
                            indent_levels = [
                                len(line) - len(line.lstrip())
                                for line in window if line.strip() != ''
                            ]
                            min_indent = min(indent_levels) if indent_levels else 0

                            # 应用缩进到 replace 块
                            replace_lines = replace.split('\n')
                            
                            replace_indent_levels = [
                                len(line) - len(line.lstrip())
                                for line in replace_lines if line.strip() != ''
                            ]
                            replace_min_indent = min(replace_indent_levels) if replace_indent_levels else 0

                            # 去除原有缩进后再加上目标缩进
                            adjusted_replace = '\n'.join(
                                (' ' * min_indent + line[replace_min_indent:] if line.strip() != '' else '')
                                for line in replace_lines
                            )

                            # 替换原内容
                            modified_lines = (
                                modified_lines[:i] +
                                adjusted_replace.split('\n') +
                                modified_lines[i+len(search_lines):]
                            )
                            modified = '\n'.join(modified_lines)
                    log_and_print('fuzzy search matched and replaced')
                else:
                    log_msg(f"Search block not found in {file_path}:\n{search}")               
                    raise ValueError("Search pattern not found in file.")

            # Create backup if needed
            modified_files.add(abs_path)
            backup_path = abs_path.with_suffix(abs_path.suffix + '.bak')
            if not os.path.exists(backup_path):
                shutil.copy(abs_path, backup_path)
                log_msg(f"Created backup at {backup_path}")

            # Write modified content
            with open(abs_path, 'w') as f:
                f.write(modified)
                
            log_msg(f"Applied {len(edits)} edits to {file_path}")
    except Exception as e:
        for modified_file in modified_files:
            # Cancel all modifications if one fails
            backup_path = modified_file.with_suffix(modified_file.suffix + '.bak')
            if os.path.exists(backup_path):
                shutil.copy(backup_path, modified_file)
                log_msg(f"Restored backup for {modified_file}")   
        raise
    
    return list(modified_files)


def gen_test_process(instance: dict):
    reproduce_test_path = f'/data/swe-fl/SRC/DebuggingAgent/data/reproduce_tests.json'
    with open(reproduce_test_path, 'r') as f:
        reproduce_tests = json.load(f)
    if instance['instance_id'] in reproduce_tests:
        reproduce_test_code = reproduce_tests[instance['instance_id']]["test_code"]
    else:
        reproduce_test_path = f'/data/swe-fl/DATA/reproduce_test/claude_reproduction_tests.json'
        with open(reproduce_test_path, 'r') as f:
            reproduce_test_code = json.load(f)[instance['instance_id']][0]

    with open(instance['testbed_src_path'] / 'reproduce.py', 'w') as f:
        f.write(reproduce_test_code)

    original_test_output = exec_debugging_test(instance)
    # original_test_output = exec_test_out + exec_test_err    
    return original_test_output, reproduce_test_code


def debugging_process(instance: dict, debugging_test_exec_result: str, reproduce_test_code: str):
    
    debugging_agent = LLMModel(model_name=MODEL_NAME, system_message=DEBUGGING_AGENT_SYSTEM_MSG, instance = instance)

    file_path, method, history = deep_dive_debugging(instance, debugging_agent, debugging_test_exec_result, reproduce_test_code)
    if file_path is None:
        raise ValueError("Failed to locate buggy method")
    
    return history


def evaluation(instance: dict):
    restore_repo(instance)
    with open(f'{EXP_DIR}/{instance["instance_id"]}/patch.json', 'r') as f:
        modify_src_instruction = json.load(f)
    apply_patch(instance, modify_src_instruction)
    
    cmd = f"cd {instance['testbed_src_path']} && conda run -n {instance['conda_env_name']} {instance['test_cmd']}"
    # result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    std_out, std_err = execute_command(cmd, 1200, verbose=False)
    
    save_dir = f'{EXP_DIR}/{instance["instance_id"]}'
    eval_log_path = os.path.join(save_dir, 'evaluation.log')
    
    with open(eval_log_path, 'w') as f:
        f.write(std_out + std_err)
    
    report = get_eval_report_for_log(instance, eval_log_path)
    
    return report



def function_invoke(previous_round_output, function_call_dict, instance, agent: LLMModel, judge = False):
    function_name = function_call_dict['function']
    args = function_call_dict['args']
    file_path = args[0]
    
    if not os.path.exists(file_path):
        file_path = os.path.join(instance['testbed_src_path'], file_path)
    
    
    if function_name == 'search_method_in_file' or function_name == 'search_class_in_file':
        element_name = args[1]
        return get_element_from_name(instance, file_path, element_name, element_type = function_name.split('_')[1])

    elif function_name == 'search_code_in_file':
        code_snippet = args[1]
        return get_element_from_name(instance, file_path, code_snippet, element_type = 'code_snippet')
    elif function_name == 'search_method_in_codebase' or function_name == 'search_class_in_codebase':
        element_name = args[0]
        result = retrieve_code_element_in_database(instance, element_name, element_type = function_name.split('_')[1], relative_path = True)
        if judge:
            return result
        source_line = function_call_dict['source_line']
        api_response = {}
        api_response[source_line] = result
        return filter_and_choose_code_element(instance, agent, previous_round_output, api_response)
    elif function_name == 'search_code_in_codebase':
        code_snippet = args[0]
        result = retrieve_code_element_in_database(instance, code_snippet, element_type = 'code_snippet', relative_path = True)
        if judge:
            return result
        source_line = function_call_dict['source_line']
        api_response = {}
        api_response[source_line] = result
        return filter_and_choose_code_element(instance, agent, previous_round_output, api_response)
    else:
        source_line = function_call_dict['source_line']
        raise ValueError(f"Unknown function call: {source_line}")


def collect_repair_code(instance: dict, debugging_history: str = None, attempt_times: int = 2):
    repair_agent = LLMModel(model_name=MODEL_NAME, system_message=DEBUGGING_AGENT_SYSTEM_MSG, instance = instance)
    repair_head_prompt = REPAIR_COLLECT_HEAD.format(
    project=instance['repo'].split('/')[1],
    issue=instance['problem_statement']
)   
    if debugging_history:
        repair_head_prompt += 'A debugging agent has tried to trace the abnormal program and locate the root cause of the bug. This is its debugging history:\n' + debugging_history + '\n'
    repair_initial_prompt = repair_head_prompt + COLLECT_INSTRUCT
    response = query_model_with_retry(repair_agent, repair_initial_prompt, judge_api_call, instance)
    retrieve_history = 'You have called API to retrieve some code and this is your API call and reply history:\n' + '=' * 50 + '\nYour Output:\n' + response + '\n' + '=' * 50 + '\n'
    
    collect_retries = 0
    
    max_collect_times = attempt_times
    
    while collect_retries < max_collect_times:
        api_result = process_api_call(response, instance, repair_agent)
        if api_result == 'ready':
            log_and_print('Ready to generate')
            break
        else:
            collect_retries += 1
            log_and_print(f'API call {collect_retries}/{max_collect_times}')
            api_result_prompt = build_api_call_reply_promopt(api_result)
            retrieve_history = update_history(retrieve_history, api_result_prompt)
            query_prompt = repair_head_prompt + retrieve_history + COLLECT_INSTRUCT
            response = query_model_with_retry(repair_agent, query_prompt, judge_api_call, instance)
            retrieve_history = update_history(retrieve_history, '\nYour Output:\n' + response)
    
    repair_prompt = repair_head_prompt + retrieve_history + REPAIR_INSTRUCT
    return repair_prompt

def generate_patch(instance: dict, repair_prompt: str):
    repair_agent = LLMModel(model_name=MODEL_NAME, system_message=DEBUGGING_AGENT_SYSTEM_MSG, instance = instance)
    success = False
    retries = 0
    while retries < 4:
        try:
            modify_src_instruction = None
            modify_src_response = query_model_with_retry(repair_agent, repair_prompt, extract_json_instruction, instance)
            modify_src_instruction = extract_json_instruction(modify_src_response)
            modified_files = apply_patch(instance, modify_src_instruction)
            with open(f'{EXP_DIR}/{instance["instance_id"]}/patch.json', 'w') as f:
                json.dump(modify_src_instruction, f, indent=4)
            success = True
            break
        except Exception as e:
            log_and_print(f"Error applying patch: {str(e)}, Retrying..")
            if modify_src_instruction:
                repair_prompt += f"\nERROR! Your Reponse: {modify_src_instruction}.\nYour response format is invalid: {str(e)}\nPlease try again.\n"
                repair_prompt += MODIFY_SOURCE_CODE_INSTRUCT
            retries += 1
            
    if not success:
        log_and_print("Failed to apply patch after multiple attempts.")
        raise ValueError("Failed to apply patch after multiple attempts.")

    return modify_src_response
    
    
def review_patch(instance: dict, patched_output: str, original_output: str, test_code: str, patch_context: str):
    review_prompt = REVIEW_PATCH_INSTRUCT.format(
        project=instance['repo'].split('/')[1],
        issue=instance['problem_statement'],
        test_code=test_code,
        patch_context=patch_context,
        patched_output=patched_output,
        original_output=original_output
    )
    review_model = LLMModel(model_name=MODEL_NAME, system_message='', instance = instance)
    response = query_model_with_retry(review_model, review_prompt, judge_review_reply, instance)
    return response, extract_review_reply(response)

    
def debugging_agent(bug_list_path: str, mode: str = 'debugging'):
    start_time = time.time()
    with open(bug_list_path,'r') as f:
        bug_list = json.load(f)
    for instance_id in bug_list:
        # if instance_id != 'sympy__sympy-20801':
        #     continue
        evaluate_report_path = f'{EXP_DIR}/{instance_id}/evaluation_report.json'
        if os.path.exists(evaluate_report_path):
            with open(evaluate_report_path, 'r') as f:
                evaluate_report = json.load(f)
            if evaluate_report['status'] == 'RESOLVED_FULL':
                print(f'{instance_id} has been repaired')
                continue
        try:
            log_path = Path(f"{EXP_DIR}/{instance_id}/{instance_id}.log")
            init_logger(log_path)
            
            print('start load_instance_data')
            instance = load_instance_data(instance_id)
            
            
            print('start init_instance_testbed')
            init_instance_testbed(instance)
            original_test_exec_result, reproduce_test_code = gen_test_process(instance)
            original_test_exec_result_depth1 = exec_debugging_test(instance, depth = -1)
            backup_repo(instance)
            total_max_exception_retry_times = 4
            
            max_regenerate_times = 4
            cur_times = 0
            success = False
            review_result = None
            while cur_times < total_max_exception_retry_times:
                try:
                    restore_repo(instance)
                    detailed_chat_dir = f"{EXP_DIR}/{instance_id}/chat"
                    if os.path.exists(detailed_chat_dir):
                        shutil.rmtree(detailed_chat_dir)
                        
                    if mode == 'debugging':
                        print('start debugging_process')
                        history = debugging_process(instance, original_test_exec_result, reproduce_test_code)
                        print('start repair_process')
                        repair_prompt = collect_repair_code(instance, history, attempt_times = 2)
                        curr_regenerate_times = 0
                        modify_src_response = generate_patch(instance, repair_prompt)
                        # retry_history = '='*50 + '\n' + modify_src_response + '\n' + '='*50 + '\n'
                        while curr_regenerate_times <= max_regenerate_times:
                            patched_test_exec_result = exec_debugging_test(instance, depth = -1)
                            reviewer_feedback, review_result = review_patch(instance, patched_test_exec_result, original_test_exec_result_depth1, reproduce_test_code, modify_src_response)
                            if review_result:
                                success = True
                                break
                            if curr_regenerate_times == max_regenerate_times:
                                break
                            
                            curr_regenerate_times += 1
                            log_and_print(f"Unable to pass patch LLM review. Retry...({curr_regenerate_times}/{max_regenerate_times})")
                            restore_repo(instance)
                            # retry_prompt = repair_prompt + REGENERATION_INSTRUCT.format(
                            #     history = modify_src_response,
                            #     patched_output = patched_test_exec_result,
                            #     reviewer_feedback = reviewer_feedback
                            # )
                            # modify_src_response = generate_patch(instance, retry_prompt)
                            # retry_history = update_history(retry_history, modify_src_response)
                            modify_src_response = generate_patch(instance, repair_prompt)
                    
                    elif mode == 'wo_debugging':
                        repair_prompt = collect_repair_code(instance, attempt_times=4)
                        modify_src_response = generate_patch(instance, repair_prompt)
                        # success = True
                        curr_regenerate_times = 0
                        while curr_regenerate_times <= max_regenerate_times:
                            patched_test_exec_result = exec_debugging_test(instance, depth = -1)
                            reviewer_feedback, review_result = review_patch(instance, patched_test_exec_result, original_test_exec_result_depth1, reproduce_test_code, modify_src_response)
                            if review_result:
                                success = True
                                break
                            if curr_regenerate_times == max_regenerate_times:
                                break
                            
                            curr_regenerate_times += 1
                            log_and_print(f"Unable to pass patch LLM review. Retry...({curr_regenerate_times}/{max_regenerate_times})")
                            restore_repo(instance)
                            
                            modify_src_response = generate_patch(instance, repair_prompt)
                    
                    if success:
                        break
                    else:
                        log_and_print("Unable to pass reviewer")
                except Exception as e:
                    log_and_print(f"Whole Process crushed: {e}")
                finally:
                    cur_times += 1
                    if not success:
                        log_and_print(f'\nRestart...({cur_times}/{total_max_exception_retry_times}')

            log_and_print('Debugging process completed. Start evaluation')
            report = evaluation(instance)
            if review_result is not None:
                report['llm_review'] =  review_result
            eval_report_path = os.path.join(f'{EXP_DIR}/{instance["instance_id"]}', 'evaluation_report.json')
            with open(eval_report_path, 'w') as f:
                json.dump(report, f, indent=4)


        except Exception as e:
            log_and_print(f"Crush in bug {instance_id}: {e}")
            traceback.print_exc()
            continue
        

    end_time = time.time()
    print(f"Total time taken: {end_time - start_time} seconds")



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--bug_list_path", type=str, help="Path to the bug list JSON file")
    parser.add_argument("--mode", type=str, default='debugging', help="Mode for the debugging agent")
    args = parser.parse_args()

    now = datetime.now().strftime("%m%d%H%M")
    EXP_DIR = f'/data/swe-fl/SRC/DebuggingAgent/exp/{args.mode}_{args.bug_list_path.split("/")[-1].split(".")[0]}_{now}'

    debugging_agent(args.bug_list_path, args.mode)
    
