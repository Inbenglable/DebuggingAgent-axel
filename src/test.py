import os
import re
import sys
import json
import time
import shutil   
import subprocess
from pathlib import Path
from datasets import load_dataset
from swe_log import init_logger, log_msg, log_and_print
from model import LLMModel, extract_json_instruction
from retrieve_src import retrieve_code_and_comment
from decorator_manager import modify_decorators_libcst
from prompt import GEN_DEBUGGING_TEST, PYSNOOPER_INTRO, DEBUGGING_AGENT_SYSTEM_MSG, \
    START_DEBUGGING, DEBUGGING_LOOP, MODIFY_SOURCE_CODE, TOO_LONG_EXEC_RESULT


sys.path.append(os.path.abspath('/data/SWE/SRC/validation/src'))
from utils import get_test_directives
from constants import MAP_VERSION_TO_INSTALL


MODEL_NAME = 'gpt-4o-2024-08-06'
# MODEL_NAME = 'claude-3-5-sonnet-20241022'

TESTBED_DIR = Path("/data/SWE/SRC/approach/tmp/testbed/")
CHECKOUT_REPO_DIR = Path("/data/SWE/DATA/swe-checkout-verified/gold/")

CONDA_ACTIVATE_PATH = 'source /root/miniforge3/bin/activate'


remove_timestamps = lambda s: re.sub(
    r'(Elapsed time:\s*\d{2}:\d{2}:\d{2}\.\d+|\b\d{2}:\d{2}:\d{2}\.\d+\b)(?:\r?\n)?',
    '',
    s
)




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

    raw_repo_path = CHECKOUT_REPO_DIR / instance['instance_id']
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
    install_pysnooper_cmd = 'pip install pysnooper'
    
    setup_repo_env_cmd = f"cd {instance['testbed_src_path']} && {CONDA_ACTIVATE_PATH} {instance['conda_env_name']} && \
           {install_pysnooper_cmd} && {instance['conda_env_install_cmd']} && echo SUCCESS"

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
    dataset = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")  
    instance_index = dataset['instance_id'].index(instance_id)  
    instance = {}

    for attr in dataset[instance_index].keys():
        instance[attr] = dataset[attr][instance_index]

    instance['conda_env_name'] = instance_id.split('-')[0] + '__' + instance['version']

    owner_proj_name = (instance_id.split('-')[0]).replace('__', '/')
    
    instance['conda_env_install_cmd'] = MAP_VERSION_TO_INSTALL[owner_proj_name][instance['version']]['install']

    log_and_print(instance['problem_statement'])
    
    log_and_print(instance['FAIL_TO_PASS'])

    log_and_print(instance['conda_env_install_cmd'])

    test_type = MAP_VERSION_TO_INSTALL[owner_proj_name][instance['version']]['test_cmd']
    test_directives = get_test_directives(instance)
    
    instance['test_cmd'] = f"{test_type} {' '.join(test_directives)}"
    log_and_print(instance['test_cmd'])

    instance['testbed_src_path'] = TESTBED_DIR / instance['instance_id'] / instance['conda_env_name']

    log_and_print(str(instance['testbed_src_path']))
    
    return instance



def gen_debugging_test(instance: dict, debugging_agent: object) -> str:
    claude_reproduce_test_path = Path(f"/data/SWE/SRC/approach/data/claude_reproduce_test/{instance['instance_id']}.py")
    with open(claude_reproduce_test_path, 'r') as f:
        reproduce_test_code = f.read()

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
        PYSNOOPER_INTRO=PYSNOOPER_INTRO
    )

    log_and_print('gen_debugging_test')

    gen_debugging_test_response = debugging_agent.query_model(gen_debugging_test_prompt, retain_memory=True, json_flag=True)

    debugging_test_instruction = extract_json_instruction(gen_debugging_test_response)
    
    return debugging_test_instruction



def write_debugging_test(instance: dict, debugging_test: json):
    with open(instance['testbed_src_path'] / 'debugging_test.py', 'w') as f:
        f.write(debugging_test['debugging_test'])
    return



def exec_debugging_test(instance: dict) -> str:
    cmd = (
        f"cd {instance['testbed_src_path']} && "
        f"{CONDA_ACTIVATE_PATH} {instance['conda_env_name']} && "
        "python debugging_test.py"
    )
    
    exec_out, exec_err = map(remove_timestamps, execute_command(cmd))
    
    total_lines = sum(len(output.strip().splitlines()) for output in [exec_out, exec_err] if output)
    
    return exec_out + exec_err if total_lines <= 1500 else TOO_LONG_EXEC_RESULT




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



def label_runtime_info_code(instance: dict, debugging_instruction: dict, action: str='add'):
    for label_runtime_info in debugging_instruction['runtime_info']:
        file_path, target_name = label_runtime_info.split(':')
        abs_file_path = instance['testbed_src_path'] / file_path
        modify_decorators_libcst(abs_file_path, [target_name], action=action)
    return



def analyse_debugging_test(instance: dict, debugging_agent, debugging_test_exec_result):
    start_debugging_prompt = START_DEBUGGING.format(
        debugging_test_exec_result = debugging_test_exec_result
    )

    log_and_print('start_debugging')

    start_debugging_response = debugging_agent.query_model(start_debugging_prompt, retain_memory=True, json_flag=True)

    start_debugging_instruction = extract_json_instruction(start_debugging_response)

    if not start_debugging_instruction['is_debugging_test_successfully_generated']:
        raise ValueError("Debugging test was not successfully generated.")
    
    start_debugging_instruction['move_to_step_3'] = False

    return start_debugging_instruction



def deep_dive_debugging(instance: dict, debugging_agent: object, debugging_instruction: dict):

    debugging_depth = 1

    while debugging_instruction['move_to_step_3'] != 'True' and debugging_depth < 5:

        review_src_str = get_review_src(instance, debugging_instruction)
        
        label_runtime_info_code(instance, debugging_instruction, action='add')

        debugging_test_exec_result = exec_debugging_test(instance)

        debugging_loop_prompt = DEBUGGING_LOOP.format(
            debugging_test_exec_result = debugging_test_exec_result,
            review_src=review_src_str
        )

        label_runtime_info_code(instance, debugging_instruction, action='remove')

        log_and_print(f'deep_dive_debugging depth: {debugging_depth}')

        debugging_loop_response = debugging_agent.query_model(debugging_loop_prompt, retain_memory=True, json_flag=True)

        debugging_instruction = extract_json_instruction(debugging_loop_response)

        debugging_depth += 1

    return


def apply_patch(instance: dict, debugging_instruction: dict):
    """
    Apply code modifications to the source files based on the debugging instructions.

    Args:
        instance (dict): Contains information about the current instance, including the testbed source path.
        debugging_instruction (dict): Contains the lists of modified code snippets and their corresponding file ranges.

    The `debugging_instruction` dictionary is expected to have the following structure:
    {
        "modify_code": ["YOUR MODIFIED CODE", "..."],
        "modify_range": ["FILE_PATH:LINE_A-LINE_B", "..."]
    }

    Each entry in `modify_code` corresponds to the entry in `modify_range` by index.
    """
    modify_codes = debugging_instruction.get("modify_code", [])
    modify_ranges = debugging_instruction.get("modify_range", [])

    if len(modify_codes) != len(modify_ranges):
        log_msg("Mismatch between the number of modify_code and modify_range entries.")
        raise ValueError("The lengths of 'modify_code' and 'modify_range' lists must be equal.")

    # Group modifications by file
    modifications_by_file = {}
    for code, range_str in zip(modify_codes, modify_ranges):
        try:
            file_path, line_range = range_str.split(':')
            line_a, line_b = map(int, line_range.split('-'))
            if file_path not in modifications_by_file:
                modifications_by_file[file_path] = []
            modifications_by_file[file_path].append({
                'modify_code': code,
                'line_a': line_a,
                'line_b': line_b
            })
        except Exception as e:
            log_msg(f"Error parsing modify_range '{range_str}': {e}")
            raise e

    # Apply modifications file by file
    for file_path, modifications in modifications_by_file.items():
        abs_file_path = instance['testbed_src_path'] / file_path

        if not abs_file_path.exists():
            log_msg(f"File does not exist: {abs_file_path}")
            raise FileNotFoundError(f"File not found: {abs_file_path}")

        # Sort modifications in descending order of line_a to prevent line number shifts
        sorted_modifications = sorted(modifications, key=lambda x: x['line_a'], reverse=True)

        try:
            # Read the original file
            with open(abs_file_path, 'r') as file:
                lines = file.readlines()

            # Backup the original file before modification
            backup_file = abs_file_path.with_suffix(abs_file_path.suffix + '.bak')
            if not backup_file.exists():
                shutil.copy(abs_file_path, backup_file)
                log_msg(f"Backup created at {backup_file}")

            for idx, mod in enumerate(sorted_modifications):
                code = mod['modify_code']
                line_a = mod['line_a']
                line_b = mod['line_b']

                # Validate line numbers
                if line_a < 1 or line_b > len(lines) or line_a > line_b:
                    log_msg(f"Invalid line range {line_a}-{line_b} for file {abs_file_path}")
                    raise ValueError(f"Invalid line range: {line_a}-{line_b} for file {abs_file_path}")

                # Replace the specified lines with the new code
                new_code_lines = code.split('\n')
                # Maintain original indentation based on the first line in the range
                original_indentation = re.match(r'\s*', lines[line_a - 1]).group()
                new_code_indented = [
                    original_indentation + line if line.strip() != "" else line
                    for line in new_code_lines
                ]
                new_code_with_newlines = [line + '\n' for line in new_code_indented]

                # Replace the lines in the original file
                lines[line_a - 1:line_b] = new_code_with_newlines

                log_msg(f"Applied patch to {file_path}: Lines {line_a}-{line_b} (Modification {idx + 1} in file)")

            # Write the modified lines back to the file after all modifications
            with open(abs_file_path, 'w') as file:
                file.writelines(lines)

        except Exception as e:
            log_msg(f"Failed to apply patches to {file_path}: {e}")
            raise e



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
    log_path = Path(f"/data/SWE/SRC/approach/tmp/log/{instance_id}.log")

    init_logger(log_path)
    
    instance = load_instance_data(instance_id)

    init_instance_testbed(instance)

    debugging_process(instance)



    # reproduce_issue(instance)
    # get_covered_filetree(instance)



    
    pass


if __name__ == '__main__':
    main()


