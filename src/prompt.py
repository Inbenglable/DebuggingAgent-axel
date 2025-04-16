DEBUGGING_AGENT_SYSTEM_MSG = 'You are a debugging agent tasked with precisely using tools to resolve issues and submit pull requests.'

DEBUGGING_START_AFTER_TESTING = '''
You need to trace the abnormal program to resolve project issues and submit pull requests.
Now you need to reolve the following issue in the **{project}** project:
#### ISSUE
{issue}

Based on this issue, the testing agent has generated a reproducible test:
{test_code}

This is the corresponding output and runtime information:
{terminal_output}

'''

# Note that a method showing abnormal program behavior may not be the buggy method since it could be an upstream method that caling the buggy method. Buggy method is the method that contains the buggy code needed to be fixed.
CHOOSE_METHOD_INSTRUCT = '''
You need to trace the abnormal program behavior step by step to identify the root cause of the bug and locate the buggy method that contains the code to be fixed.
Now, please first analyze the current observed code and the abnormal program behavior. 

Then, if you can already locate the buggy method and buggy code, reply with:  
Buggy method: `{FILE_PATH}:{METHOD_NAME}`
Otherwise, continue tracing by selecting the next method to observe. Reply with: 
Observed method: `{FILE_PATH}:{METHOD_NAME}`
Note that {FILE_PATH} refers to the path relative to the repository. And if you want to observe a method inside a class, please specify the class name and method name in the format of `ClassName.method_name` as METHOD_NAME.
'''

# CHOOSE_METHOD_INSTRUCT = '''
# You need to trace the abnormal program behavior step by step to identify the root cause and locate the buggy method—the one containing the code that needs to be fixed.
# Note that a method showing abnormal program behavior may not be the buggy method since it could be an upstream method that caling the buggy method. Buggy method is the method that contains the buggy code needed to be fixed.
# Now, please first analyze the current observed code and the abnormal program behavior. 

# Note that a method showing abnormal program behavior may not be the buggy method since it could be an upstream method that caling the buggy method. Buggy method is the method that contains the buggy code needed to be fixed.
CHOOSE_SCOPE_INSTRUCT = '''
You need to trace the abnormal program behavior step by step to identify the root cause of the bug and locate the buggy method that contains the code to be fixed.
Now, please first analyze the current observed code and the abnormal program behavior. 

Then, if you can already locate the buggy method and buggy code, reply with:  
Buggy method: `{FILE_PATH}:{METHOD_NAME}`
Otherwise, continue tracing by telling me the code line scope that you want to deeper observe, we will show you the deeper downstream run-time information of the scope you select. Please reply with:
Observed scope: `{FILE_PATH}:{START_LOC}-{END_LOC}`
Note that {FILE_PATH} refers to the path relative to the repository.
'''


BEGIN_INTRO = '''
You need to trace the abnormal program to resolve project issues and submit pull requests.
Now you need to reolve the following issue in the **{project}** project:
#### ISSUE
{issue}

Based on this issue, the testing agent has generated a reproducible test:
{test_code}

'''

DEBUGGING_CHOOSE_SCOPE = '''
This is the tracing and analysis history:
{history}

Now you choose downstream method {observe_method} to further observe, tracing the abnormal program behavior.
This is the method code:
{method_code}

This is the runtime information of {observe_method}:

{runtime_info}

'''

DEBUGGING_CHOOSE_METHOD = '''
This is the tracing and analysis history:
{history}

Now you choose {observe_method}'s code snippet 
{code_snippet}
for further observation, tracing the abnormal program behavior.

This is the runtime information of the code snippet you choose to observed in {observe_method}:

{runtime_info}

'''

ANALYSE_TEST = '''
This is the output from running the debugging test. Next, you need to determine whether the debugging test was executed correctly.

{debugging_test_exec_result}

- **If the debugging test was generated successfully**, proceed to **Step 2**:
- **If the debugging test was not generated successfully**, please regenerate it.

Your analysis should be thorough, and it's acceptable for it to be very detailed.

In **Step 2**, you will perform multiple iterative steps to progressively resolve the issue.

At the end of your analysis, provide the specific information in the following JSON format:


{{
    "is_debugging_test_successfully_generated": "True/False",
    "debugging_test": "YOUR TEST CODE if the previous was not successfully generated",
}}

'''


GEN_DEBUGGING_TEST = '''

You are a debugging agent tasked with precisely using tools to resolve issues and submit pull requests.

**Current Task:**  
Resolve the following issue in the {project} project:
#### ISSUE
{issue}

Based on this issue, the testing agent has generated a reproducible test:

{reproduce_test_code}

**Test Execution Results:**

{reproduce_result}

Follow these steps to resolve the issue:

1. Create a minimal debugging test based on the reproduce test.
2. Debug by reviewing the relevant source code and monitoring runtime information.
3. Once you have identified the root cause, modify the code with minimal changes.
4. Rerun the reproduction script to confirm that the issue is fixed.

Focus on Step 1: generate a debugging test. At the end of your analysis, provide the specific code in the following **JSON format**.
Note: You should clearly specify the tests you are debugging as much as possible. Minimizing the amount of code will better assist you in analyzing runtime information later.


{{
"debugging_test" : "import ... # Your debugging test code here"
}}

'''


MODIFY_SOURCE_CODE_HEAD = '''
You are a bug repair agent to resolve issues and submit pull requests.
Now You need to reolve the following issue in the **{project}** project:
#### ISSUE
{issue}

Based on this issue, the testing agent has generated a reproducible test that can trigger the bug:
{test_code}

This is the tracing and analysis history of how we tracing and locating the buggy method and the root cause:
{history}

Now, you need to fix the buggy method {method_name}, whose method code is as follow:
{method_code}

'''

MODIFY_SOURCE_CODE_INSTRUCT = '''
Please ensure that your patch does not disrupt the original functionality of the code.
Generate *SEARCH/REPLACE* patches to fix the issue.

Every *SEARCH/REPLACE* edit must use this format:
1. The file path
2. The start of search block: <<<<<<< SEARCH
3. A contiguous chunk of lines to search for in the existing source code
4. The dividing line: =======
5. The lines to replace into the source code
6. The end of the replace block: >>>>>>> REPLACE

Here is an example of a *SEARCH/REPLACE* edit:

```python
### mathweb/flask/app.py
<<<<<<< SEARCH
from flask import Flask
=======
import math
from flask import Flask
>>>>>>> REPLACE
```

At the end of your analysis, provide edit result in the following JSON format:
{
  "search_replace_edits": [
    "{SEARCH_REPLACE_EDIT_1}",
    "{SEARCH_REPLACE_EDIT_2}",
  ]
}
'''


TOO_LONG_EXEC_RESULT = '''
The debugging test execution result is too long to display here. Please re-select your `runtime_info` lists to narrow down the scope of your analysis.
'''

REPAIR_COLLECT_HEAD = '''
You are a bug repair agent to resolve issues and submit pull requests.
Now You need to reolve the following issue in the **{project}** project:
#### ISSUE
{issue}
'''

COLLECT_INSTRUCT = '''
Based on these information, you need to think about how to resolve the issue and fix the bug.
Now, please first analyze whether you need to retrieve any source code or if you're ready to generate the patch. Note that before generating a patch for a method, you must first obtain its source code.
Then you have two options. (Choose only one of them):

### IF GENERATE PATCH
If you've gathered enough code to generate the patch, stop invoking the search APIs.
At this point, instead of invoking function call, please reply with:
Ready generation: `True` 

### IF YOU NEED TO RETRIEVE SOURCE CODE
If you need to know any more source code to help you generate the patch, use the search APIs to retrieve code.
You can use the following APIs to search source code.
1. `search_method_in_file(file_path: str, method_name: str)`: Search for the method code in the specified file.
2. `search_class_in_file(file_path: str, class_name: str)`: Search for the class code in the specified file.
3. `search_code_in_file(file_path: str, code: str)`: Search for a code snippet in the specified file, return its surrounding code.

You should finally reply in the following format:
```python
search_method_in_file("FILE_PATH", "METHOD_NAME")
search_class_in_file("FILE_PATH", "CLASS_NAME")
search_code_in_file("FILE_PATH", "SOME_CODE")
```
Note the format should obeys the following rules:
1. Enclose all API calls in a single python code block (i.e., start with ```python, followed by the API calls, then close the block with ```).
2. You may invoke any of these APIs as many times as needed, including not at all.
3. The file path is relative to the repository.
4. All arguments must be enclosed in double quotes and the number of arguments must be correct.
5. If the method you want to search belongs to a class, it is recommended specify the class name and method name in the format of `ClassName.method_name` as METHOD_NAME. Otherwise multiple methods with the same name (but in different classes) may be returned.


Now, please first analyze whether you need to retrieve any source code or if you're ready to generate the patch. Note that before generating a patch for a method, you must first obtain its source code.
Then choose one of the two options above and follow the format to reply.
'''

# Then you have two options. (Choose only one of them):
# 1. If you need to know any more source code to help you generate the patch, use the search APIs to retrieve code.
# 2. If you already have enough information, go ahead and generate the patch.


# **Important:** Once you've gathered enough code to generate the patch, stop invoking the search APIs. Retrieving too much code can cause confusion and make it harder to generate an accurate fix.


REPAIR_INSTRUCT = '''
Now, you need to generate patches to resolve the issue. Please ensure that your patch does not disrupt the original functionality of the code.
You should generate *SEARCH/REPLACE* format patches to fix the issue.
Every *SEARCH/REPLACE* edit must use this format:
1. The file path
2. The start of search block: <<<<<<< SEARCH
3. A contiguous chunk of lines to search for in the existing source code
4. The dividing line: =======
5. The lines to replace into the source code
6. The end of the replace block: >>>>>>> REPLACE

Here is an example of a *SEARCH/REPLACE* edit:

```python
### mathweb/flask/app.py
<<<<<<< SEARCH
from flask import Flask
=======
import math
from flask import Flask
>>>>>>> REPLACE
```

You should finally provide edit result in the following JSON format (each {SEARCH_REPLACE_EDIT} is a *SEARCH/REPLACE* edit):
{
  "search_replace_edits": [
    "{SEARCH_REPLACE_EDIT_1}",
    "{SEARCH_REPLACE_EDIT_2}",
  ]
}

'''