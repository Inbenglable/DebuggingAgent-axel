import os
import re
import sys
import json
import time
import shutil   
import subprocess
from pathlib import Path
from datasets import load_dataset
from swe_log import init_logger, log_msg, log_and_print, remove_ansi_escape_sequences
from model import LLMModel, extract_json_instruction
from retrieve_src import retrieve_code_and_comment
from decorator_manager import modify_decorators_libcst
from prompt import GEN_DEBUGGING_TEST, DEBUGGING_AGENT_SYSTEM_MSG, \
    START_DEBUGGING, DEBUGGING_LOOP, MODIFY_SOURCE_CODE, TOO_LONG_EXEC_RESULT


sys.path.append(os.path.abspath('/data/swe-fl/SRC/SWE-Bench-Validation/src'))
from utils import get_test_directives
from constants import MAP_VERSION_TO_INSTALL


# MODEL_NAME = 'gpt-4o-2024-05-13'
MODEL_NAME = 'gpt-4o-2024-08-06'
# MODEL_NAME = 'o1-mini-2024-09-12'
# MODEL_NAME = 'claude-3-5-sonnet-20241022'

TESTBED_DIR = Path("/data/swe-fl/TMP/testbed/")
DBGSNOOPER_DIR = Path("/data/swe-fl/SRC/pysnooper_axel/dbgsnooper")
CHECKOUT_REPO_DIR = Path("/data/swe-fl/EXP/swe-evaluation/swe-verified-checkout/gold")

# os.environ['HF_DATASETS_CACHE'] = '~/.cache/huggingface/datasets/'

CONDA_ACTIVATE_PATH = 'source /root/miniforge3/bin/activate'


remove_timestamps = lambda s: re.sub(
    r'(Elapsed time:\s*\d{2}:\d{2}:\d{2}\.\d+|\b\d{2}:\d{2}:\d{2}\.\d+\b)(?:\r?\n)?',
    '',
    s
)

print('import finished')


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
        
        shutil.copytree(raw_repo_path, testbed_path)

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

    


# instance_id ATTR: instance_id, version, conda_env_name, problem_statement
#                   conda_env_install_cmd, test_cmd, testbed_src_path
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

    instance['conda_env_name'] = instance_id.split('-')[0] + '__' + instance['version']

    owner_proj_name = (instance_id.split('-')[0]).replace('__', '/')
    
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



def gen_debugging_test(instance: dict, debugging_agent: object) -> str:
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

    gen_debugging_test_response = debugging_agent.query_model(gen_debugging_test_prompt, retain_memory=True, json_flag=True)

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




def get_review_src(instance: dict, debugging_instruction: dict) -> str:
    review_src_lst = []
    for target_src in debugging_instruction['review_src']:
        file_path, target_name = target_src.split(':')
        abs_file_path = instance['testbed_src_path'] / file_path
        retrieve_result = retrieve_code_and_comment(abs_file_path, target_name)
        # If the code snippet is too long, retrieve the skeleton code instead
        if 'start_line' in retrieve_result and \
            retrieve_result['end_line'] - retrieve_result['start_line'] > 500:
            retrieve_result = retrieve_code_and_comment(abs_file_path, target_name, skeleton=True)

        review_src_lst.append(retrieve_result)
    
    review_src_str = '\n\n'.join(
        [f"{src['name']}\n{src['code']}" for src in review_src_lst if 'code' in src]
    )
    return review_src_str



# def label_runtime_info_code(instance: dict, debugging_instruction: dict, action: str='add'):
#     for label_runtime_info in debugging_instruction['runtime_info']:
#         file_path, target_name = label_runtime_info.split(':')
#         abs_file_path = instance['testbed_src_path'] / file_path
#         modify_decorators_libcst(abs_file_path, [target_name], action=action)
#     return

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
        
        obs_file_path = str(instance['testbed_src_path'] / file_path)
        runtime_info[obs_file_path] = (start_line, end_line)

    log_and_print(runtime_info)
    return runtime_info


def analyse_debugging_test(instance: dict, debugging_agent: LLMModel, debugging_test_exec_result):
    start_debugging_prompt = START_DEBUGGING.format(
        debugging_test_exec_result = debugging_test_exec_result
    )

    log_and_print('start_debugging')

    start_debugging_response = debugging_agent.query_model(start_debugging_prompt, retain_memory=True, json_flag=True)

    start_debugging_instruction = extract_json_instruction(start_debugging_response)

    if not start_debugging_instruction['is_debugging_test_successfully_generated']:
        raise ValueError("Debugging test was not successfully generated.")
    
    # if retain_memory and self.memory.chat_memory.messages:
    #     messages = self.memory.chat_memory.messages.copy()
    # else:
    #     messages = [SystemMessage(content=self.system_message)]
    
            
    start_debugging_instruction['move_to_step_3'] = False

    return start_debugging_instruction


def remove_runtime_info_code(debugging_agent: object):
    pattern = r'<runtime-info>.*?</runtime-info>'
    modified = debugging_agent.modify_memory_content(
        target_pattern=pattern,
        replacement="", 
    )
    log_and_print(f'remove_runtime_info_code: Modify {modified} runtime-info code')


def deep_dive_debugging(instance: dict, debugging_agent: object, debugging_instruction: dict):

    debugging_depth = 1

    while debugging_instruction['move_to_step_3'] != 'True' and debugging_depth < 6:

        review_src_str = get_review_src(instance, debugging_instruction)

        # remove previous runtime-info memory in llm
        remove_runtime_info_code(debugging_agent)
        
        runtime_info = extract_runtime_info(instance, debugging_instruction)

        debugging_test_exec_result = exec_debugging_test(instance, runtime_info)

        debugging_loop_prompt = DEBUGGING_LOOP.format(
            debugging_test_exec_result = debugging_test_exec_result,
            review_src=review_src_str
        )

        log_and_print(f'deep_dive_debugging depth: {debugging_depth}')

        debugging_loop_response = debugging_agent.query_model(debugging_loop_prompt, retain_memory=True, json_flag=True)

        debugging_instruction = extract_json_instruction(debugging_loop_response)

        debugging_depth += 1

    return


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
    # save edits in log dir
    with open(f'/data/swe-fl/SRC/DebuggingAgent/log/{instance["instance_id"]}_edits.log', 'w') as f:
        f.write('\n'.join(edits))
    # Group edits by file path
    file_edits = {}
    for edit in edits:
        lines = edit.split('\n')
        try:
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
            raise ValueError("Malformed search/replace edit block") from e

    # Process each file
    for file_path, edits in file_edits.items():
        abs_path = instance['testbed_src_path'] / file_path
        
        if not abs_path.exists():
            log_msg(f"File not found: {abs_path}")
            raise FileNotFoundError(f"File not found: {abs_path}")

        # Read original content
        with open(abs_path, 'r') as f:
            content = f.read()

        # Apply edits sequentially
        modified = content
        for search, replace in edits:
            if search not in modified:
                log_msg(f"Search block not found in {file_path}:\n{search}")
                raise ValueError("Search pattern not found in file")
            
            modified = modified.replace(search, replace, 1)  # Replace first occurrence

        # Create backup if needed
        backup_path = abs_path.with_suffix(abs_path.suffix + '.bak')
        if not backup_path.exists():
            shutil.copy(abs_path, backup_path)
            log_msg(f"Created backup at {backup_path}")

        # Write modified content
        with open(abs_path, 'w') as f:
            f.write(modified)
            
        log_msg(f"Applied {len(edits)} edits to {file_path}")



def modify_code_resolve_issue(instance: dict, debugging_agent: object):
    
    modify_src_prompt = MODIFY_SOURCE_CODE
    
    log_and_print('modify_src')

    modify_src_response = debugging_agent.query_model(modify_src_prompt, retain_memory=True, json_flag=True)

    modify_src_instruction = extract_json_instruction(modify_src_response)

    apply_patch(instance, modify_src_instruction)

    # TODO: should we apply review stage like tools+claude?


    pass



def debugging_process(instance: dict):
    
    debugging_agent = LLMModel(model_name=MODEL_NAME, system_message=DEBUGGING_AGENT_SYSTEM_MSG)
    

    # Step 1: generate debugging test
    debugging_test_instruction = gen_debugging_test(instance, debugging_agent)
    
    write_debugging_test(instance, debugging_test_instruction)

    debugging_test_exec_result = exec_debugging_test(instance)


    # Step 2: start debugging (first analyse if debugging test is successfully generated)
    start_debugging_instruction = analyse_debugging_test(instance, debugging_agent, debugging_test_exec_result)
    
    deep_dive_debugging(instance, debugging_agent, start_debugging_instruction)

    
    # Step 3: modify source code 
    # First review the code range you want to modify: +-5 line
    # Then modify the code with range 
    # Finally review the code change.

    modify_code_resolve_issue(instance, debugging_agent)
     
    

def main():

    instance_id = 'astropy__astropy-12907'
    log_path = Path(f"/data/swe-fl/SRC/DebuggingAgent/log/{instance_id}.log")
    
    detailed_chat_dir = Path(f"/data/swe-fl/SRC/DebuggingAgent/chat")
    if os.path.exists(detailed_chat_dir):
        shutil.rmtree(detailed_chat_dir)
    
    init_logger(log_path)
    
    print('start load_instance_data')
    instance = load_instance_data(instance_id)

    # DEBUG
    print('start init_instance_testbed')
    init_instance_testbed(instance)
    print('start debugging_process')

    debugging_process(instance)



    # reproduce_issue(instance)
    # get_covered_filetree(instance)



    
    pass


if __name__ == '__main__':
    main()


