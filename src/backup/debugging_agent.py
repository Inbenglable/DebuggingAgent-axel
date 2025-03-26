import os
import re
import sys
import json
import time
import shutil   
import subprocess
from pathlib import Path
from pydantic import BaseModel
from datasets import load_dataset
from add_pysnooper_decorator import add_pysnooper_decotator
from log import init_logger, print_banner, print_block, log_msg
from retrieve_code_context import retrieve_code_and_comment
from model import request_openai_api
from prompt import REPRODUCE_ISSUE, DEBUGGING_ISSUE_PYSNOOPER, \
    PYSNOOPER_DESCRIPTION, RETRIEVE_CODE_CONTEXT, FILE_TREE_COVERAGE, LINE_COVERAGE

from repo_structure import get_file_tree_str, get_covered_lines


def execute_command(command: str) -> tuple:
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
        log_msg(stdout)
        if stderr:
            log_msg(stderr)
        return stdout, stderr
    except subprocess.CalledProcessError as e:
        log_msg("CMD exec failed:")
        log_msg(e.stdout)
        log_msg("STDERR:")
        log_msg(e.stderr)
        return e.stdout, e.stderr


def init_testbed(target_instance_id: str):
    global SWE_DATASET

    SWE_DATASET = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")    

    log_path = Path(f"/data/SWE/SRC/approach/tmp/log/{target_instance_id}.log")
    init_logger(log_path)


    # Setup testbed for target instance
    raw_repo_dir = Path("/data/SWE/DATA/swe-checkout-verified/gold/")
    testbed_dir = Path("/data/SWE/SRC/approach/tmp/testbed/")
    
    testbed_dir.mkdir(parents=True, exist_ok=True)

    raw_repo_path = raw_repo_dir / target_instance_id
    testbed_path = testbed_dir / target_instance_id

    try:
        if not raw_repo_path.exists():
            raise FileNotFoundError(f"Source directory does not exist: {raw_repo_path}")
        
        # DEBUG
        if testbed_path.exists():
            shutil.rmtree(testbed_path)
            log_msg(f"Remove exist testbed_path: {testbed_path}")
        
        shutil.copytree(raw_repo_path, testbed_path)

    except Exception as e:
        log_msg(f"Error copying repository: {e}")
        raise
    
    

    # Retrieve target instance info
    target_instance_index = SWE_DATASET['instance_id'].index(target_instance_id)
    
    target_repo_name = target_instance_id.split('__')[0]
    target_version = SWE_DATASET['version'][target_instance_index]

    # TODO
    sys.path.append('/data/SWE/SRC/validation/src/')
    from constants import MAP_VERSION_TO_INSTALL

    conda_env_name = target_instance_id.split('-')[0] + '__' + target_version

    conda_activate_cmd = f"source /root/miniforge3/bin/activate {conda_env_name}"

    target_instance_info = {
        'version': target_version,
        'testbed_path': testbed_path,
        'repo_name' : target_repo_name,
        'repo_path' : testbed_path / conda_env_name,
        'instance_id' : target_instance_id,
        'conda_env_name' : conda_env_name,
        'conda_bin_path' : '/root/miniforge3/bin/activate',
        'conda_activate_cmd' : conda_activate_cmd,
        'issue_description': SWE_DATASET['problem_statement'][target_instance_index],
    }

    repo2proj_name = (target_instance_id.split('-')[0]).replace('__', '/')
    
    target_conda_env_install_cmd = MAP_VERSION_TO_INSTALL[repo2proj_name][target_version]['install']

    install_pysnooper_cmd = 'pip install pysnooper'
    
    setup_repo_env_cmd = f"cd {target_instance_info['repo_path']} && {target_instance_info['conda_activate_cmd']} && \
          {install_pysnooper_cmd} && {target_conda_env_install_cmd} && echo SUCCESS"

    log_msg(f"Reinstalling repository environment: {target_instance_id}")

    # DEBUG
    execute_command(setup_repo_env_cmd)

    return target_instance_info
    


def extract_content(wrapped_json_str: str) -> str:
    # ```json\nCONTENT\n```
    match_json = re.search(r'```json\s*\n(.*?)\n```', wrapped_json_str, re.DOTALL)
    if match_json:
        try:
            json_obj = json.loads(match_json.group(1).strip())
            return json_obj
        except json.JSONDecodeError as e:
            log_msg(f"Error decoding JSON: {e}")
            raise e
    else:
        raise ValueError("No JSON content found in the response.")

    # ```\nCONTENT\n```
    # match_generic = re.search(r'```\s*\n(.*?)\n```', wrapped_json_str, re.DOTALL)
    # if match_generic:
    #     return match_generic.group(1).strip()

    # return wrapped_json_str.strip()


# class ReproduceTask(BaseModel):
#     reproduce_code: str
#     description: str
    


# reproduce_task_schema = {
#     "type": "object",
#     "properties": {
#         "description": {"type": "string"},
#         "reproduce_code": {"type": "string", "format": "python-code"}
#     },
#     "required": ["name", "age", "email"]
# }




def start_debugging(target_instance_info: dict):

    target_instance_id = target_instance_info['instance_id']

    # model_name = 'o1-mini-2024-09-12'
    # model_name="gpt-3.5-turbo-0301"
    model_name = 'gpt-4o-2024-08-06'
    # model_name = 'claude-3-5-sonnet-20241022'
    # model_name = 'gpt-4o-2024-05-13'

    print_banner(target_instance_id)

    target_instance_index = SWE_DATASET['instance_id'].index(target_instance_id)

    reproduce_issue_prompt = REPRODUCE_ISSUE.format(
        issue_description=SWE_DATASET['problem_statement'][target_instance_index],
        pysnooper_description=PYSNOOPER_DESCRIPTION
    )
    
    print_block(reproduce_issue_prompt, 'reproduce_issue_task')
    
    reproduce_task_output = request_openai_api(reproduce_issue_prompt, model=model_name)

    print_block(reproduce_task_output, 'reproduce_task', color='magenta')

    reproduce_task_content = extract_content(reproduce_task_output)

    reproduce_test_code = reproduce_task_content['file_content']

    
    exec_test_out, exec_test_err = get_reproduce_test_coverage(target_instance_info, reproduce_task_content)

    coverage_file_path = target_instance_info['repo_path'] / 'coverage.xml'
    file_tree_str = get_file_tree_str(coverage_file_path)


    covered_file_tree_prompt = FILE_TREE_COVERAGE.format(
        issue_description = SWE_DATASET['problem_statement'][target_instance_index],
        reproduce_code = reproduce_test_code,
        reproduce_exec_result = exec_test_out + exec_test_err,
        coverage_file_tree = file_tree_str
    )

    print_block(covered_file_tree_prompt, 'coverage_file_tree_prompt')

    llm_file_fl_output = request_openai_api(covered_file_tree_prompt, model=model_name)

    print_block(llm_file_fl_output, 'llm_file_fl_output', color='magenta')

    llm_file_fl_content = extract_content(llm_file_fl_output)

    # print_block(llm_file_fl['observe_file'], 'observe_file', color='magenta')
    # print_block(llm_file_fl['description'], 'description', color='magenta')

    # get line coverage corresponding code
    covered_lines = get_covered_lines(coverage_file_path, llm_file_fl_content['observe_file'])


    covered_line_prompt = LINE_COVERAGE.format(
        issue_description = SWE_DATASET['problem_statement'][target_instance_index],
        reproduce_code = reproduce_test_code,
        reproduce_exec_result = exec_test_out + exec_test_err,
        selected_covered_file = llm_file_fl_content['observe_file'],
        covered_lines = covered_lines,
        pysnooper_description = PYSNOOPER_DESCRIPTION
    )

    print_block(covered_line_prompt, 'covered_line_prompt')

    llm_observe_function_output = request_openai_api(covered_line_prompt, model=model_name)

    print_block(llm_observe_function_output, 'llm_observe_function_output', color='magenta')

    llm_observe_function = extract_content(llm_observe_function_output)

    # llm_observe_function = json.loads(extract_content(llm_observe_function_raw[0]))

    # print_block(str(llm_observe_function['pysnooper_observe_function']), 'pysnooper_observe_function', color='magenta')
    # print_block(llm_file_fl_content['description'], 'description', color='magenta')

    # sys.exit(0)

    debugging_depth = 0
    llm_instuctions = llm_observe_function
    pysnooper_obs_set = set(llm_observe_function['pysnooper_observe_function'])

    while debugging_depth < 10:
        # Run test with pysnooper
        exec_test_out, exec_test_err = run_test_with_pysnooper(target_instance_info, llm_instuctions)


        debugging_issue_prompt = DEBUGGING_ISSUE_PYSNOOPER.format(
                issue_description=SWE_DATASET['problem_statement'][target_instance_index],
                reproduce_code = reproduce_test_code,
                pysnooper_obs_list = str(llm_instuctions),
                reproduce_exec_result = exec_test_out + exec_test_err,
            )
        
        print_block(debugging_issue_prompt, 'debugging_issue_prompt')

        llm_debugging_output = request_openai_api(debugging_issue_prompt, model=model_name)
        print_block(llm_debugging_output, 'llm_debugging_output', color='magenta')
        llm_debugging = extract_content(llm_debugging_output)

        print(llm_debugging)

        if llm_debugging['modify_location'] != 'NULL':
            break
        
        if 'ORIGIN' not in llm_debugging['file_content']:
            reproduce_test_code = llm_debugging['file_content']
        else:
            llm_debugging['file_content'] = reproduce_test_code

        pysnooper_obs_set.update(llm_debugging['pysnooper_observe_function'])
        llm_debugging['pysnooper_observe_function'] = list(pysnooper_obs_set)

        llm_instuctions = llm_debugging

        
    print_block(str(llm_debugging['modify_location']), 'modify_location', color='magenta')
    print_block('```python\n'+str(llm_debugging['modify_code'])+'\n```', 'modify_code', color='magenta')
    print_block(llm_debugging['description'], 'description', color='magenta')








    # print_banner('EXEC OUTPUT')
    # print(reproduce_test_exec_result)


    # debugging_depth = 0
    # retrieve_context = ''
    # fault_location_raw = ''
    # llm_debugging_result = llm_reproduce_result
    

    # while debugging_depth < 10:
        
    #     print_banner(f'DEBUGGING DEPTH {debugging_depth}')

    #     # Construct debugging issue prompt
    #     prev_llm_output = 'reproduce_code: ' + llm_debugging_result['file_content'] + '\n' \
    #         + 'pysnooper_observe_function: ' + str(llm_debugging_result['pysnooper_observe_function']) + '\n' \
    #         + 'retrieve_code_context: ' + retrieve_context

    #     debugging_issue_prompt = DEBUGGING_ISSUE_PYSNOOPER.format(
    #         issue_description=SWE_DATASET['problem_statement'][target_instance_index],
    #         pysnooper_description=PYSNOOPER_DESCRIPTION, 
    #         retrieve_code_context=RETRIEVE_CODE_CONTEXT,
    #         prev_reproduce_content= prev_llm_output,
    #         prev_run_reproduce=reproduce_test_exec_result
    #         )
        

    #     # Query llm for debugging instruction
    #     llm_debugging_raw = request_openai_api(
    #         debugging_issue_prompt, max_tokens=8000, batch_size=1, model='gpt-4o'
    #         )
        
    #     llm_debugging_result = json.loads(extract_content(llm_debugging_raw[0]))


    #     # Check if fault location is found, just break
    #     if llm_debugging_result['fault_location'] != 'NULL':
    #         fault_location_raw = llm_debugging_result['fault_location']
    #         break

        
    #     # Retrieve code context
    #     print_block(str(llm_debugging_result['retrieve_code_context']), 'retrieve_code_context', color='magenta')
    #     retrieve_context = '\n'
    #     for curr_retrive_context in llm_debugging_result['retrieve_code_context']:
    #         file_relative_path, element_name = curr_retrive_context.split(':')
    #         file_abs_path = target_instance_info['repo_path'] / file_relative_path
    #         retrieve_result = retrieve_code_and_comment(file_abs_path, element_name)
    #         if 'code' in retrieve_result:
    #             retrieve_context += retrieve_result['code'] + '\n\n'
        
    #     # Update reproduce test code if not lable 'ORIGIN'
    #     print_block("```python\n" + llm_debugging_result['file_content'] + "\n```", 'reproduce_test', color='magenta')

    #     if 'ORIGIN' not in llm_debugging_result['file_content']:
    #         reproduce_test_code = llm_debugging_result['file_content']
    #     else:
    #         llm_debugging_result['file_content'] = reproduce_test_code


    #     # Update pysnooper_observe_function (add new functions into set)
    #     pysnooper_observe_function_set.update(set(llm_debugging_result['pysnooper_observe_function']))
    #     llm_debugging_result['pysnooper_observe_function'] = list(pysnooper_observe_function_set)


        
    #     print_block(str(llm_debugging_result['pysnooper_observe_function']), 'pysnooper_observe_function', color='magenta')

    #     print_block(llm_debugging_result['description'], 'description', color='magenta')
        
    #     # Execute reproduce test code
    #     reproduce_test_exec_result = run_test(target_instance_info, llm_debugging_result)

    #     print_banner('EXEC OUTPUT')
    #     print(reproduce_test_exec_result)

    #     debugging_depth += 1


    # print_block(str(fault_location_raw), 'fault_location', color='magenta')
    # print_block(llm_debugging_result['description'], 'description', color='magenta')


    # return
    




def run_test_with_pysnooper(target_instance_info: dict, llm_instruction: dict):
    # First, cd into target_instance_info['testbed_path'] and write reproduce.py (llm_reproduce_result['file_content'])
    # reproduce_file_path = target_instance_info['repo_path'] / 'reproduce.py'
    # with open(reproduce_file_path, 'w') as f:
    #     f.write(llm_instruction['file_content'])

    # Label pysnooper functions
    pysnooper_observe_function = llm_instruction['pysnooper_observe_function']
    for func in pysnooper_observe_function:
        file_path, func_name = func.split(':')
        source_file_path = target_instance_info['repo_path'] / file_path
        add_pysnooper_decotator(source_file_path, func_name)


    # Run reproduce.py
    exec_test_out, exec_test_err = execute_command(f"cd {target_instance_info['repo_path']} && \
                                     {target_instance_info['conda_activate_cmd']} && python reproduce.py")
    

    return exec_test_out, exec_test_err


def get_reproduce_test_coverage(target_instance_info: dict, llm_instruction: dict):
    reproduce_file_path = target_instance_info['repo_path'] / 'reproduce.py'
    with open(reproduce_file_path, 'w') as f:
        f.write(llm_instruction['file_content'])

    exec_test_out, exec_test_err = execute_command(f"cd {target_instance_info['repo_path']} && \
                                    {target_instance_info['conda_activate_cmd']} && coverage run reproduce.py")
    
    execute_command(f"cd {target_instance_info['repo_path']} && \
                                    {target_instance_info['conda_activate_cmd']} && coverage xml")
    
    
    return exec_test_out, exec_test_err


def main():
    # target_instance_id = 'astropy__astropy-12907'
    # target_instance_id = 'astropy__astropy-14182'
    # target_instance_id = 'astropy__astropy-14365'
    # target_instance_id = 'astropy__astropy-7166'
    # target_instance_id = 'astropy__astropy-7336'
    # target_instance_id = 'astropy__astropy-7606'
    target_instance_id = 'astropy__astropy-7671'
    # target_instance_id = 'django__django-14155'
    
    target_instance_info = init_testbed(target_instance_id)
    
    # exec_test_out, exec_test_err = get_reproduce_test_coverage(target_instance_info, {})

    # coverage_file_path = target_instance_info['repo_path'] / 'coverage.xml'
    # file_tree_str = get_file_tree_str(coverage_file_path)
    # print(file_tree_str)

    start_debugging(target_instance_info)
    
    pass


if __name__ == '__main__':
    main()


