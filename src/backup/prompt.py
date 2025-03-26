
REPRODUCE_ISSUE = '''

Consider the following issue description:

{issue_description}

Please analyze the issue and create a script `reproduce.py` that reproduces the issue.

'''




# RETRIEVE_CODE_CONTEXT = '''

# You can choose the function/class you want to observe. Here is an example of the output:

#     35  class A(Input):
#     36    def __init__(self, a, b):
#     37      self.a = a
#     38      self.b = b
#     39      ...

# Just enter "retrieve_code_context" field, and you will be able to observe it.

# '''




# PYSNOOPER_DESCRIPTION = '''
# You can use the pysnooper library to observe the functions in the script and pysnooper is installed and ready to use.
# All you need to do is to specify the functions you want to observe wherever in the target buggy repository or in the reproduce.py.


# For example, this is part of your reproduce.py script:

# ```python
# import pysnooper
# from MODULE_A.submodule_B import foo, bar
# foo(in_0)
# bar(in_1)
# ```

# If you want to observe the functions `foo` and `bar` in repository `REPO_A`, you need to specify the functions in the JSON output as follows:

# "pysnooper_observe_function": ["FILE_PATH:foo", "FILE_PATH:bar"]

# And the FILE_PATH is the path to the file containing the function, relative to the root of the repository, like `MODULE_A/MODULE_B.py`.

# If you want to observe the reproduce.py script, you can modify reproduce.py by your own:

# ```python
# import pysnooper

# @pysnooper.snoop()  
# def main():
#     ...
# ``` 

# '''

# # TOOD description

# REPRODUCE_ISSUE = '''

# Consider the following issue description:

# ```bash
# {issue_description}
# ```


# 首先请分析issue 并 create a script `reproduce.py` that reproduces the issue. 

# 在你回答的最后请使用如下json格式输出你的结果:
# ```json
# {{
#   "file_content": "reproduce.py code",
#   "description": "brief description of your analysis"
# }}
# ```


# '''


# FILE_TREE_COVERAGE = '''

# Consider the following issue description:

# ```bash
# {issue_description}
# ```

# You have created a script `reproduce.py` that tries to reproduces the error.

# ```python
# {reproduce_code}
# ```

# And this is output of the reproduce.py by running `python reproduce.py`:

# ```bash
# {reproduce_exec_result}
# ```

# Based on the coverage information obtained from running reproduce.py, which is displayed in a file tree format. Please select a file from the covered files to view the specific covered code.

# ```bash 
# {coverage_file_tree}
# ```

# 在你回答的最后请使用如下json格式输出你的结果:
# ```json
# {{
#   "observe_file": "FILE_PATH",
#   "description": "DESCRIPTION"
# }}

# - Replace `DESCRIPTION` with your analysis.
# ```
# '''

# LINE_COVERAGE = '''

# Consider the following issue description:

# {issue_description}


# You have created a script `reproduce.py` that tries to reproduces the error.

# ```python
# {reproduce_code}
# ```

# And this is output of the reproduce.py by running `python reproduce.py`:

# ```bash
# {reproduce_exec_result}
# ```

# Based on the coverage information obtained from running reproduce.py, which is displayed in a file tree format. You choose to select {selected_covered_file} from the covered files to view the specific covered code.

# ```bash
# {covered_lines}
# ```

# {pysnooper_description}


# 在你回答的最后请使用如下json格式输出你的结果:
# ```json
# {{
#   "pysnooper_observe_function": ["FILE_PATH:FUNCTION_NAME_A", "FILE_PATH:FUNCTION_NAME_B"],
#   "description": "DESCRIPTION"
# }}
# ```
# - Replace `pysnooper_observe_function` with the relevant file paths and function names to observe.
# - Replace `DESCRIPTION` with your analysis.


# '''



# DEBUGGING_ISSUE_PYSNOOPER = '''

# Consider the following issue description:


# ```bash
# {issue_description}
# ```


# You have created a script `reproduce.py` that tries to reproduces the error.

# ```python
# {reproduce_code}
# ```
# Moreover, you have selected the function list that use pysnooper to observe runtime information: 
# {pysnooper_obs_list}

# And this is output of the reproduce.py by running `python reproduce.py`:

# ```bash
# {reproduce_exec_result}
# ```


# **Task:** Analyze `reproduce.py` and its output to determine whether the issue can be fixed:

# 1. **If fixable**, provide:
#    - Fault location: File path and line range.
#    - Fix: Brief description and code to resolve the issue.
# 2. **If not fixable**, modify `reproduce.py` and `pysnooper_observe_function` to collect more data for defect identification.

# 在你回答的最后请使用如下json格式输出你的结果:
# ```json
# {{
#   "modify_location": ["FILE_PATH:LINE_A-LINE_B",...],
#   "modify_code": "CODE",
#   "file_content": "CODE",
#   "pysnooper_observe_function": ["FILE_PATH:FUNCTION_NAME_A", "FILE_PATH:FUNCTION_NAME_B"],
#   "description": "DESCRIPTION"
# }}
# ```

# **Instructions:**

# - **If fixable:**
#   - Specify `modify_location` with file path and line range.
#   - Add `modify_code` with the fix.
#   - Set `file_content` and `pysnooper_observe_function` to `"NULL"`.
#   - Use `description` to analysis the root cause of the defect and fix.

# - **If not fixable:**
#   - Set `modify_location` and `modify_code` to `"NULL"`.
#   - Update `file_content` with added code or `"ORIGIN"` if unchanged.
#   - List relevant file paths and functions in `pysnooper_observe_function`.
#   - Use `description` to explain your analysis.

# '''




# Now you need to analyze the current `reproduce.py` and the output to determine whether the defect location can be identified:
# - If yes, please provide the file and line number range where the defect is located. Replace `DESCRIPTION` with a brief explanation of the defect and how to fix.
# - If not, please modify `reproduce.py` and `pysnooper_observe_function` to obtain more information to help you locate the defect.

# **YOU MUST FOLLOW the JSON output format, and ensure your output consists SOLELY of this JSON:**

# ```json
# {{
#   "fault_location": ["FILE_PATH:LINE_A-LINE_B",...],
#   "file_content": "CODE",
#   "pysnooper_observe_function": ["FILE_PATH:FUNCTION_NAME_A", "FILE_PATH:FUNCTION_NAME_B"],
#   "retrieve_code_context": ["FILE_PATH:FUNCTION_NAME_A", "FILE_PATH:CALSS_NAME_B"],
#   "description": "DESCRIPTION"
# }}
# ```

# If the defect location cannot be identified currently, set `fault_location` to `"NULL"` and then:
# - Replace `CODE` with the actual Python code you write in the script, or fill in `"ORIGIN"` to indicate no changes to `reproduce.py`.
# - Replace `["FILE_PATH:FUNCTION_NAME_A",...]` with a list of file paths and function names you want to observe with `pysnooper`.
# - Replace `["FILE_PATH:FUNCTION_NAME_A", "FILE_PATH:CALSS_NAME_B"]` with a list of file paths and function/class names you want to observe with `retrieve_code_context`.
# - Replace `DESCRIPTION` with a brief explanation of what the code does and how it reproduces the error.

# If the defect location can be accurately identified, only fill in `fault_location` and set the other JSON fields to `NULL`.

# <debugging_fault_location>

# Now you need to analyze the current reproduce.py and the output to determine whether the defect location can be identified. 

# - If yes, please provide the file and line number range (`"fault_location": ["FILE_PATH:LINE_A-LINE_B",...]`) where the defect is located. Replace `DESCRIPTION` with a brief explanation of the defect location.
# Set the other JSON fields to `NULL`.

# - If not, please modify `reproduce.py` and `pysnooper_observe_function` to obtain more information to help you locate the defect.
# Set `fault_location` to `"NULL"`.
# Replace `CODE` with the actual Python code you write in the script, or fill in `"ORIGIN"` to indicate no changes to `reproduce.py`.
# Replace `["FILE_PATH:FUNCTION_NAME_A",...]` with a list of file paths and function names you want to observe with `pysnooper`.
# Replace `DESCRIPTION` with a brief explanation of what the code does and how it reproduces the error.



# </debugging_fault_location>




# REPAIR_OVERVIEW = '''I've uploaded a python code repository in the directory /repo. Consider the following issue description:

# <issue_description>

# {issue_description}

# </issue_description>

# Can you help me implement the necessary changes to the repository so that the requirements specified in the <issue_description> are met?
# I've already taken care of all changes to any of the test files described in the <issue_description>. This means you DON'T have to modify the testing logic or any of the tests in any way!

# Your task is to make the minimal changes to non-tests files in the /repo directory to ensure the <issue_description> is satisfied.

# Follow these steps to resolve the issue:
# 1. As a first step, it might be a good idea to explore the repo to familiarize yourself with its structure.
# 2. Create a script to reproduce the error and execute it with `python <filename.py>` using the BashTool, to confirm the error
# 3. Edit the sourcecode of the repo to resolve the issue
# 4. Rerun your reproduce script and confirm that the error is fixed!
# '''

