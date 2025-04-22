import os
import re
import sys
import json
import time
import shutil   
import tiktoken
import subprocess
import ast
import textwrap
import inspect
import traceback
from pathlib import Path
# from datasets import load_dataset
from swe_log import init_logger, log_msg, log_and_print, remove_ansi_escape_sequences
from model import LLMModel
from retrieve_src import retrieve_code_element, retrieve_code_element_in_database
from run_report import get_eval_report_for_log
from prompt import GEN_DEBUGGING_TEST, DEBUGGING_AGENT_SYSTEM_MSG, \
    ANALYSE_TEST, MODIFY_SOURCE_CODE_HEAD, MODIFY_SOURCE_CODE_INSTRUCT, TOO_LONG_EXEC_RESULT, DEBUGGING_START_AFTER_TESTING, \
    CHOOSE_SCOPE_INSTRUCT, CHOOSE_METHOD_INSTRUCT, BEGIN_INTRO, DEBUGGING_CHOOSE_SCOPE, DEBUGGING_CHOOSE_METHOD, REPAIR_COLLECT_HEAD, \
    COLLECT_INSTRUCT, REPAIR_INSTRUCT, FILTER_INSTRUCT

sys.path.append(os.path.abspath('/data/swe-fl/SRC/SWE-Bench-Validation/src'))
from utils import get_test_directives
from constants import MAP_VERSION_TO_INSTALL

MODEL_NAME = 'gpt-4o'
# MODEL_NAME = 'qwen2.5:32b-instruct-fp8'
# MODEL_NAME = 'gpt-4o-2024-05-13'
# MODEL_NAME = 'gpt-4o-2024-08-06'
# MODEL_NAME = 'o1-mini-2024-09-12'
# MODEL_NAME = 'claude-3-5-sonnet-20241022'

TESTBED_DIR = Path("/data/swe-fl/TMP/testbed/")
DBGSNOOPER_DIR = Path("/data/swe-fl/SRC/pysnooper_axel/dbgsnooper")
CHECKOUT_REPO_DIR = Path("/data/swe-fl/EXP/swe-evaluation/swe-verified-checkout/gold")

EXP_DIR = "/data/swe-fl/SRC/DebuggingAgent/exp_wo_debugging"

# os.environ['HF_DATASETS_CACHE'] = '~/.cache/huggingface/datasets/'

CONDA_ACTIVATE_PATH = 'source /root/miniforge3/bin/activate'


remove_timestamps = lambda s: re.sub(
    r'(Elapsed time:\s*\d{2}:\d{2}:\d{2}\.\d+|\b\d{2}:\d{2}:\d{2}\.\d+\b)(?:\r?\n)?',
    '',
    s
)

print('import finished')


def extract_json_instruction(wrapped_json_str: str) -> str:
    # ```json\nCONTENT\n```
    match_json = re.search(r'```json\s*\n(.*?)\n```', wrapped_json_str, re.DOTALL)
    # log_and_print(match_json)
    if match_json:
        try:
            json_obj = json.loads(match_json.group(1).strip())
            return json_obj
        except json.JSONDecodeError as e:
            log_msg(f"Error decoding JSON: {e}")
            raise e
    else:
        raise ValueError("No JSON content found in the response.")


def extract_trace_reply(response: str):

    # 匹配 buggy/observed method，支持带反引号和加粗 Markdown **
    method_pattern = r"\*{0,2}([Bb]uggy [Mm]ethod|[Oo]bserved [Mm]ethod)\*{0,2}:\s*`?([^:`\n]+):([^:`\n]+)`?"

    # 匹配 observed scope，可以是单行或范围，也支持加粗 key
    scope_pattern = r"\*{0,2}[Oo]bserved [Ss]cope\*{0,2}:\s*`?([^:`\n]+):(\d+)(?:-(\d+))?`?"

    if match := re.search(method_pattern, response):
        return {
            "type": match.group(1),
            "file": match.group(2).strip(),
            "method": match.group(3).strip()
        }
    elif match := re.search(scope_pattern, response):
        start_line = int(match.group(2))
        end_line = int(match.group(3)) if match.group(3) else start_line
        return {
            "type": "Observed scope",
            "file": match.group(1).strip(),
            "start_line": start_line,
            "end_line": end_line
        }
    else:
        raise ValueError("Invalid trace reply format.")
    
    
def execute_command(command: str) -> tuple:
    log_and_print(command)
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            executable='/bin/bash'
        )
        stdout = result.stdout
        stderr = result.stderr
        return stdout, stderr
    except subprocess.CalledProcessError as e:
        log_msg("CMD exec failed:")
        log_msg(e.stdout)
        log_msg("STDERR:")
        log_msg(e.stderr)
        return e.stdout, e.stderr

def extract_filter_reply(response: str):
    code_block_pattern = r"```(.*?)```"
    match = re.search(code_block_pattern, response, re.DOTALL)
    if match:
        text = match.group(1).strip()
    else:
        raise ValueError("No Python code block found in the response.")
    
    filter_reply_results = []
    for line in text.splitlines():
        if not line.strip():
            continue
        filter_reply_reulst = {}
        line = line.strip()
        if ':' not in line:
            continue
        file_path, name = line.split(':')
        filter_reply_reulst['file_path'] = file_path.strip()
        
        line_range_match = re.match(r'^(\d+)-(\d+)$', name)
        if line_range_match:
            start = int(line_range_match.group(1))
            end = int(line_range_match.group(2))
            filter_reply_reulst['start_line'] = start
            filter_reply_reulst['end_line'] = end
        else:
            filter_reply_reulst['name'] = name.strip()
        filter_reply_results.append(filter_reply_reulst)
    if len(filter_reply_results) == 0:
        raise ValueError("No valid filter reply results found.")
    
    return filter_reply_results    
        
    
    

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
    
    if api_reply_dict[key][0]['type'] == 'line_range':
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

    log_msg(f"Setup testbed environment: {instance['instance_id']}")
    log_msg(setup_repo_env_cmd)
    
    std_out, std_err = execute_command(setup_repo_env_cmd)

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


# def exec_debugging_test_with_limited_length(instance: dict, file_scope_dict=None, depth=2, loop=None):
#     if loop:
#         return exec_debugging_test(instance, file_line_dict, depth = 1)
#     else:
#         output = exec_debugging_test(instance, file_line_dict, depth = 1)
#         encoding = tiktoken.get_encoding("cl100k_base")
#         token_len =  len(encoding.encode(output))
#         if token_len > 2000:
            


def gen_debugging_test(instance: dict, debugging_agent: LLMModel) -> str:
    # reproduce_test_path = Path(f"/data/SWE/SRC/approach/data/claude_reproduce_test/{instance['instance_id']}.py")
    # with open(reproduce_test_path, 'r') as f:
    #     reproduce_test_code = f.read()
    reproduce_test_path = f'/data/swe-fl/DATA/reproduce_test/claude_reproduction_tests.json'
    with open(reproduce_test_path, 'r') as f:
        reproduce_test_code = json.load(f)[instance['instance_id']][0]

    with open(instance['testbed_src_path'] / 'reproduce.py', 'w') as f:
        f.write(reproduce_test_code)

    exec_test_out, exec_test_err = execute_command(f"cd {instance['testbed_src_path']} && \
                                {CONDA_ACTIVATE_PATH} {instance['conda_env_name']} && python reproduce.py")

    # construct debugging test prompt
    gen_debugging_test_prompt = GEN_DEBUGGING_TEST.format(
        project=instance['repo'].split('/')[1],
        issue=instance['problem_statement'],
        reproduce_test_code=reproduce_test_code,
        reproduce_result=exec_test_out + exec_test_err,
    )

    log_and_print('gen_debugging_test')

    gen_debugging_test_response = query_model_with_retry(debugging_agent, gen_debugging_test_prompt, judge_response_with_json, instance)

    debugging_test_instruction = extract_json_instruction(gen_debugging_test_response)
    
    return debugging_test_instruction



def write_debugging_test(instance: dict, debugging_test: json):
    with open(instance['testbed_src_path'] / 'debugging_test.py', 'w') as f:
        f.write(debugging_test['debugging_test'])
    return


def count_lines(test_path: Path) -> int:
    with test_path.open('r', encoding='utf-8') as file:
        return sum(1 for _ in file)


def exec_debugging_test(instance: dict, file_scope_dict=None, depth=2, loop=None) -> str:
    test_path = instance['testbed_src_path'] / 'debugging_test.py'
    
    # if file_scope_dict is None (Step 1), then just observe the whole test file
    file_scope_dict = file_scope_dict or {str(test_path): (0, count_lines(test_path))}

    dict_json = json.dumps(file_scope_dict)
    
    cmd = [
        "conda", "run", "-n", instance['conda_env_name'],
        "python", "run_debugging_test.py",
        "--test-path", test_path,
        "--file-scope-dict", dict_json
    ]
    
    if depth is not None:
        cmd += ["--depth", str(depth)]
    if loop is not None:
        cmd += ["--loop", str(loop)]
    
    result = subprocess.run(cmd, capture_output=True, text=True)

    result_clean = remove_timestamps(
        remove_ansi_escape_sequences(result.stdout + result.stderr)
        )

    # result_clean = remove_timestamps(result.stdout + result.stderr)
    
    # remove ""SOURCE IS UNAVAILABLE" lines
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



def extract_runtime_info(instance, debugging_instruction: list) -> dict:
    runtime_info = {}
    for target_src in debugging_instruction['runtime_info']:
        file_path, observe_range = target_src.split(':')
        # e.g., astropy/modeling/separable.py:66-102
        if '-' in observe_range:
            start_line, end_line = map(int, observe_range.split('-'))
        # e.g., astropy/modeling/core.py:57
        else:
            start_line = end_line = int(observe_range)
        
        abs_file_path = str(instance['testbed_src_path'] / file_path)
        runtime_info[abs_file_path] = (start_line, end_line)

    log_and_print(runtime_info)
    return runtime_info


def analyse_debugging_test(instance: dict, debugging_agent: LLMModel, debugging_test_exec_result):
    start_debugging_prompt = ANALYSE_TEST.format(
        debugging_test_exec_result = debugging_test_exec_result
    )

    log_and_print('start_debugging')

    start_debugging_response = query_model_with_retry(debugging_agent, start_debugging_prompt, judge_response_with_json, instance)

    start_debugging_instruction = extract_json_instruction(start_debugging_response)

    if not start_debugging_instruction['is_debugging_test_successfully_generated']:
        raise ValueError("Debugging test was not successfully generated.")
    
    #TODO the regenerate process 
    start_debugging_instruction['move_to_step_3'] = False

    return start_debugging_instruction

def update_history(history: str, new_entry: str) -> str:
    new_history = history + new_entry + '\n' + '='*50 + '\n'
    return new_history

def get_element_from_name(instance: dict, file_name: str, element_name: str, element_type: str, enable_line_number: bool = False, relative_path: bool = True):
    if not os.path.exists(file_name):
        abs_file_path = instance['testbed_src_path'] / file_name
    else:
        abs_file_path = file_name
    retrieve_result = retrieve_code_element(abs_file_path, element_name, element_type, enable_line_number, relative_path, instance)
    return retrieve_result

def judge_response_with_json(response: str, instance) -> bool:
    try:
        extract_json_instruction(response)
    except Exception as e:
        raise Exception(f'Expected json format in response but ERROR occurs: {e}')
    return True

def judge_method_choose(response: str, instance) -> bool:
    try:
        trace_reply = extract_trace_reply(response)
        if trace_reply['type'].lower() == 'buggy method' or trace_reply['type'].lower() == 'observed method':
            file_name = trace_reply['file']
            if not os.path.exists(file_name):
                abs_file_path = instance['testbed_src_path'] / file_name
            else:
                abs_file_path = file_name
            if os.path.exists(abs_file_path):
                retrieve_result = retrieve_code_element(abs_file_path, trace_reply['method'], 'method')
            else:
                raise Exception(f'File {file_name} not found')
        else:
            raise Exception(f'Expected buggy method or observed method but got {trace_reply["type"]}')
    except Exception as e:
        raise Exception(f'Exception occurs when method choosing: {e}')

    return True

    
def judge_scope_choose(response: str, instance) -> bool:
    try:
        trace_reply = extract_trace_reply(response)
        if trace_reply['type'].lower() == 'observed scope':
            file_name = trace_reply['file']
            if not os.path.exists(file_name):
                abs_file_path = instance['testbed_src_path'] / file_name
            else:
                abs_file_path = file_name
            if os.path.exists(abs_file_path):
                observed_start_line = trace_reply['start_line']
                observed_end_line = trace_reply['end_line']
                retrieve_result = retrieve_code_element(abs_file_path, f'{observed_start_line}-{observed_end_line}','scope')[0]
            else:
                raise Exception(f'File {file_name} not found')
        
        elif trace_reply['type'].lower() == 'buggy method':
            file_name = trace_reply['file']
            if not os.path.exists(file_name):
                abs_file_path = instance['testbed_src_path'] / file_name
            else:
                abs_file_path = file_name
            if os.path.exists(abs_file_path):
                retrieve_result = retrieve_code_element(abs_file_path, trace_reply['method'], 'method')
            else:
                raise Exception(f'File {file_name} not found')
        else:
            raise Exception(f'Expected observed scope or buggy method but got {trace_reply["type"]}')
                
    except Exception as e:
        raise Exception(f'Exception occurs when scope choosing: {e}')

    return True
    

def judge_ready_generation(response: str):

    pattern = r"\*{0,2}([Rr]eady [Gg]eneration)\*{0,2}:\s*`?([^:`\n]+)`?"

    if match := re.search(pattern, response):
        if match.group(2).strip().lower() == 'true':
            return True

    return False


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
            if len(inspect.signature(judge_function).parameters) == 2:
                if judge_function(response, instance):
                    success = True
                    break
            elif len(inspect.signature(judge_function).parameters) == 3:
                if judge_function(response, instance, model):
                    success = True
                    break
        except Exception as e:
            if retry_msg:
                log_and_print(retry_msg)
            log_and_print(f"Error occurred when querying model.\n{str(e)}\nRetrying..({retries}/{max_retries})")
                
    if not success:
        log_and_print("Failed to get valid model response after multiple attempts.")
        raise ValueError("Failed to get valid model response after multiple attempts.")
    
    
    return response
    
def deep_dive_debugging(instance: dict, debugging_agent: LLMModel, debugging_test_exec_result: str, reproduce_test_code: str):

    debugging_agent.clear_memory()
    initial_debugging_prompt = DEBUGGING_START_AFTER_TESTING.format(
        project=instance['repo'].split('/')[1],
        issue=instance['problem_statement'],
        test_code = reproduce_test_code,
        terminal_output = debugging_test_exec_result
    ) + CHOOSE_METHOD_INSTRUCT
    model_response = query_model_with_retry(debugging_agent, initial_debugging_prompt, judge_method_choose, instance)
    history = '\n' + '='*50 + '\n' + model_response + '\n' + '='*50 + '\n'
    debugging_depth = 1
    begin_prompt = BEGIN_INTRO.format(
        project = instance['repo'].split('/')[1],
        issue = instance['problem_statement'],
        test_code = reproduce_test_code
    )
    
    while debugging_depth < 6:
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
        model_response = query_model_with_retry(debugging_agent, choose_scope_prompt, judge_scope_choose, instance)
        history = update_history(history, model_response)
        trace_reply = extract_trace_reply(model_response)
        if trace_reply['type'].lower() == 'buggy method':
            log_and_print(f'choose buggy method: {trace_reply["file"]}:{trace_reply["method"]}')
            return trace_reply['file'], trace_reply['method'], history
        
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
                if search in modified:
                    modified = modified.replace(search, replace)  # Replace all occurrence
                    continue
                # Normalize and strip for matching
                modified_lines = modified.split('\n')
                modified_stripped_lines = [line.strip() for line in modified_lines]
                modified_normalized = '\n'.join(modified_stripped_lines)

                search_lines = search.split('\n')
                search_stripped_lines = [line.strip() for line in search_lines]
                search_normalized = '\n'.join(search_stripped_lines)

                if search_normalized in modified_normalized:
                    for i in range(len(modified_lines) - len(search_lines) + 1):
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
                            break
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

def modify_code_resolve_issue(instance: dict, debugging_agent: LLMModel, file_path: str, method: str, history: str, test_code: str):
    method_code = get_element_from_name(instance, file_path, method, element_type = 'method')[0]['code']
    modify_src_prompt = MODIFY_SOURCE_CODE_HEAD.format(
        project = instance['repo'].split('/')[1],
        issue = instance['problem_statement'],
        test_code = test_code,
        history = history,
        method_name = method,
        method_code = method_code
    ) + MODIFY_SOURCE_CODE_INSTRUCT
    
    log_and_print('modify_src')

    success = False
    retries = 0
    while retries < 3:
        try:
            modify_src_response = query_model_with_retry(debugging_agent, modify_src_prompt, judge_response_with_json, instance)

            modify_src_instruction = extract_json_instruction(modify_src_response)
            apply_patch(instance, modify_src_instruction)
            success = True
            break
        except Exception as e:
            log_and_print(f"Error applying patch: {str(e)}, Retrying..")
            if modify_src_instruction:
                modify_src_prompt += f"\nERROR! Your Reponse: {modify_src_instruction}.\nYour response format is invalid: {str(e)}\nPlease try again.\n"
                modify_src_prompt += MODIFY_SOURCE_CODE_INSTRUCT
            retries += 1

    if not success:
        log_and_print("Failed to apply patch after multiple attempts.")
        raise ValueError("Failed to apply patch after multiple attempts.")
    # TODO: should we apply review stage like tools+claude?


def debugging_process(instance: dict):
    
    debugging_agent = LLMModel(model_name=MODEL_NAME, system_message=DEBUGGING_AGENT_SYSTEM_MSG, instance = instance)
    
    debugging_test_instruction = gen_debugging_test(instance, debugging_agent)

    reproduce_test_code = debugging_test_instruction['debugging_test']
    write_debugging_test(instance, debugging_test_instruction)

    debugging_test_exec_result = exec_debugging_test(instance)

    file_path, method, history = deep_dive_debugging(instance, debugging_agent, debugging_test_exec_result, reproduce_test_code)
    if file_path is None:
        raise ValueError("Failed to locate buggy method")
    
    return history

    # modify_code_resolve_issue(instance, debugging_agent, file_path, method, history, reproduce_test_code)

def evaluation(instance: dict):
    cmd = f"cd {instance['testbed_src_path']} && conda run -n {instance['conda_env_name']} {instance['test_cmd']}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    save_dir = f'{EXP_DIR}/{instance["instance_id"]}'
    eval_log_path = os.path.join(save_dir, 'evaluation.log')
    eval_report_path = os.path.join(save_dir, 'evaluation_report.json')
    
    with open(eval_log_path, 'w') as f:
        f.write(result.stdout + result.stderr)
    
    report = get_eval_report_for_log(instance, eval_log_path)
    with open(eval_report_path, 'w') as f:
        json.dump(report, f, indent=4)
 
 
def extract_function_call(text):
    python_code_block_pattern = r"```python\n(.*?)```"
    match = re.search(python_code_block_pattern, text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    else:
        # log_and_print("No Python code block found in the response.")
        return []
    
    function_names = {"search_method_in_file", "search_class_in_file", "search_code_in_file","search_method_in_codebase","search_class_in_codebase","search_code_in_codebase"}
    results = []

    # 保留行信息，为了后面能用 lineno 取出原始字符串
    original_lines = [line for line in text.splitlines()]
    stripped_lines = [line.strip() for line in original_lines if line.strip()]
    text = '\n'.join(stripped_lines)

    try:
        # 包装为 dummy 函数使其可被解析
        code = f"def _():\n{textwrap.indent(text, '    ')}"
        tree = ast.parse(code)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                func_name = node.func.id
                if func_name in function_names:
                    args = []
                    for arg in node.args:
                        if isinstance(arg, ast.Constant):  # Python 3.8+
                            args.append(arg.value)
                        elif isinstance(arg, ast.Str):  # Python <3.8
                            args.append(arg.s)
                        else:
                            args.append(ast.unparse(arg))  # fallback

                    # 获取原始调用行（注意 -1 是因为 lineno 从 1 开始，加了 dummy 函数所以是 node.lineno - 2）
                    source_lineno = node.lineno - 2
                    if 0 <= source_lineno < len(stripped_lines):
                        source_line = stripped_lines[source_lineno]
                    else:
                        source_line = ""

                    results.append({
                        "function": func_name,
                        "args": args,
                        "source_line": source_line
                    })

        return results
    except SyntaxError as e:
        return []  # 解析错误，返回空列表



def function_invoke(previous_round_output, function_call_dict, instance, agent: LLMModel, judge = False):
    function_name = function_call_dict['function']
    args = function_call_dict['args']
    file_path = args[0]
    
    if not os.path.exists(file_path):
        file_path = instance['testbed_src_path'] / file_path
    
    
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
        raise ValueError(f"Unknown function call: {function_name}")



def repair_process(instance: dict, debugging_history: str = None):
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
    
    max_collect_times = 4
    
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
    
    
    success = False
    retries = 0
    while retries < 3:
        try:
            modify_src_response = query_model_with_retry(repair_agent, repair_prompt, judge_response_with_json, instance)
            modify_src_instruction = extract_json_instruction(modify_src_response)
            modified_files = apply_patch(instance, modify_src_instruction)
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
    
    return modified_files
    
         
    
def main():
    start_time = time.time()
    with open('/data/swe-fl/SRC/DebuggingAgent/bug_list.json','r') as f:
        bug_list = json.load(f)
    for instance_id in bug_list:
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
            
            total_max_exception_retry_times = 3
            cur_times = 0
            success = False
            while cur_times < total_max_exception_retry_times:
                try:
                    detailed_chat_dir = Path(f"{EXP_DIR}/{instance_id}/chat")
                    if os.path.exists(detailed_chat_dir):
                        shutil.rmtree(detailed_chat_dir)
                    # print('start debugging_process')
                    # history = debugging_process(instance)
                    # print('start repair_process')
                    # repair_process(instance, history)
                    repair_process(instance)
                    success = True
                    break
                except Exception as e:
                    log_and_print(f"Error occurred: {e}")
                    traceback.print_exc()
                    cur_times += 1
                    if cur_times == total_max_exception_retry_times:
                        raise ValueError("Debugging and repair process failed after multiple retries.")


            
            if success:
                log_and_print('Debugging process completed successfully. Start evaluation')
                evaluation(instance)
            else:
                log_and_print('Debugging process failed after multiple attempts. Please check the logs for more details.')

        except Exception as e:
            log_and_print(f"Crush in bug {instance_id}: {e}")
            continue
        

    end_time = time.time()
    print(f"Total time taken: {end_time - start_time} seconds")

    # astropy__astropy-13579 
    # astropy__astropy-14096
    # astropy__astropy-8872
    # astropy__astropy-13453 fail



if __name__ == '__main__':
    main()
    # instance = load_instance_data('sphinx-doc__sphinx-8595')
    # agent = LLMModel(model_name=MODEL_NAME, system_message=DEBUGGING_AGENT_SYSTEM_MSG, instance = instance)
    # with open('tmp.txt','r') as f:
    #     response = f.read()
    # result = process_api_call(response, instance, agent)
    # import pprint
    # pprint.pprint(result)


