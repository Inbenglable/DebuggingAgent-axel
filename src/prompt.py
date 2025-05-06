DEBUGGING_AGENT_SYSTEM_MSG = 'You are a debugging agent tasked with precisely using tools to resolve issues and submit pull requests.'

DEBUGGING_START_AFTER_TESTING = '''
You need to trace the abnormal program to resolve project issues and submit pull requests.
Now you need to reolve the following issue in the **{project}** project:
## ISSUE
<ISSUE>
{issue}
</ISSUE>


Based on this issue, the testing agent has generated a reproducible test:
{test_code}

This is the corresponding output and runtime information:
{terminal_output}

'''

# Note that a method showing abnormal program behavior may not be the buggy method since it could be an upstream method that caling the buggy method. Buggy method is the method that contains the buggy code needed to be fixed.
#  (Note: In some cases, there may not be an existing buggy method — for example, if the fix involves modifying a class definition or adding a new method. In these cases, as long as you have identified and located the root cause, simply select the closest related method and report it as the buggy method)
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
# (Note: In some cases, there may not be an existing buggy method — for example, if the fix involves modifying a class definition or adding a new method. In these cases, as long as you have identified and located the root cause, simply select the closest related method and report it as the buggy method)

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
## ISSUE
<ISSUE>
{issue}
</ISSUE>


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
## ISSUE
<ISSUE>
{issue}
</ISSUE>


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
## ISSUE
<ISSUE>
{issue}
</ISSUE>


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
## ISSUE
<ISSUE>
{issue}
</ISSUE>


'''



# 1. `search_method_in_file(file_path: str, method_name: str)`: Search for the method in the specified file.
# 2. `search_method_in_codebase(method_name: str)`: Search for the method in the whole project codebase. Only if you don't know the file path of the method, this API should be used. Otherwise, you should use the `search_method_in_file` API.
# 3. `search_class_in_file(file_path: str, class_name: str)`: Search for the class code in the specified file.
# 4. `search_class_in_codebase(class_name: str)`: Search for the class code in the whole project codebase. Only if you don't know the file path of the class, this API should be used. Otherwise, you should use the `search_class_in_file` API.
# 5. `search_code_in_file(file_path: str, code: str)`: Search for a code snippet in the specified file, return its surrounding code.
# 6. `search_code_in_codebase(code: str)`: Search for a code snippet in the whole project codebase. Only if you don't know the file path of the code, this API should be used. Otherwise, you should use the `search_code_in_file` API.
COLLECT_INSTRUCT = '''
Based on these information, you need to think about how to resolve the issue and fix the bug.
Now, please first analyze whether you need to retrieve any source code or if you're ready to generate the patch. Note that before generating a patch for a method, you must first obtain its source code.
Then you have two options. (Choose only one of them):

## IF GENERATE PATCH
If you've gathered enough code to generate the patch, stop invoking the search APIs.
At this point, instead of invoking function call, please reply with:
Ready generation: `True` 

## IF YOU NEED TO RETRIEVE SOURCE CODE
If you need to know any more source code to help you generate the patch, use the search APIs to retrieve code.
You can use the following APIs to search source code.
1. `search_method_in_file(file_path: str, method_name: str)`: Search for the method in the specified file.
2. `search_method_in_codebase(method_name: str)`: Search for the method in the whole project codebase. Only if you don't know the file path of the method, this API should be used. Otherwise, you should use the `search_method_in_file` API.
3. `search_class_in_file(file_path: str, class_name: str)`: Search for the class code in the specified file.
4. `search_class_in_codebase(class_name: str)`: Search for the class code in the whole project codebase. Only if you don't know the file path of the class, this API should be used. Otherwise, you should use the `search_class_in_file` API.
5. `search_code_in_file(file_path: str, code: str)`: Search for a code snippet in the specified file, return its surrounding code.
6. `search_code_in_codebase(code: str)`: Search for a code snippet in the whole project codebase. Only if you don't know the file path of the code, this API should be used. Otherwise, you should use the `search_code_in_file` API.


You should finally reply in the following format:
```python
search_method_in_file("FILE_PATH", "METHOD_NAME")
search_class_in_file("FILE_PATH", "CLASS_NAME")
search_code_in_file("FILE_PATH", "SOME_CODE")
search_method_in_codebase("METHOD_NAME")
...
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

FILTER_INSTRUCT = '''
You are a bug repair agent to resolve issues and submit pull requests.
This is the bug issue, which is in the **{project}** project:
## ISSUE
<ISSUE>
{issue}
</ISSUE>


In the previous round, you called search APIs to retrieve relevant source code that would help identify the root cause of the issue and generate a patch. However, the code you retrieved appears in multiple locations (maybe some are irrelevant but have same key). So now your task is to determine which of the retrieved contents are indeed you need, and filter out the irrelevant ones.
This is your API invocation round output:
{retrieve_round_output}

And this is the corresponding API returned result (each content is started with #### FILE_PATH:NAME):
{search_api_results}

Among the API returned contents, there may be some irrelevant ones or not. So now you need to analyze each returned content and determine whether each one is your needed.
Now, please first analyze the API returned content and determine whether each one is your needed.

Then you need to choose you needed ones with the following format:
```
FILE_PATH_1:NAME_1
FILE_PATH_2:NAME_2
...
```

Note:
1. The value of FILE_PATH:NAME, must consistent with the API returned content (but remove the prefix ####).
2. You may select one or more contents, or even all of them if they are indeed you need.
'''

REVIEW_PATCH_INSTRUCT = '''
You are a PR reviewer that needs to review the patch generated by a bug repair agent and determine whether the issue is fixed or not.
This is the bug issue, which is in the **{project}** project:
## ISSUE
<ISSUE>
{issue}
</ISSUE>


Based on this issue, the testing agent has generated a reproducible test:
## REPRODUCE TEST
```
{test_code}
```

And this is the original output when running the test (before applying the patch):
## ORIGINAL OUTPUT
```
{original_output}
```

The repair agent has tried to generate a patch to fix the issue:
## PATCH CONTEXT
<PATCH_CONTEXT>
{patch_context}
</PATCH_CONTEXT>

After applying the patch, the output of the test is:
## PATCHED OUTPUT
```
{patched_output}
```

Now, please first review the patch and analyse the test output before and after the patch, to determine whether the issue is fixed or not.

And finally, tell me whether the issue is fixed or not by replying with:
Issue resolved: `True/False`
'''

# Then you have two options. (Choose only one of them):
# 1. If you need to know any more source code to help you generate the patch, use the search APIs to retrieve code.
# 2. If you already have enough information, go ahead and generate the patch.

# **Important:** Once you've gathered enough code to generate the patch, stop invoking the search APIs. Retrieving too much code can cause confusion and make it harder to generate an accurate fix.


# 1. The file path
# 2. The start of search block: <<<<<<< SEARCH
# 3. A contiguous chunk of lines to search for in the existing source code
# 4. The dividing line: =======
# 5. The lines to replace into the source code
# 6. The end of the replace block: >>>>>>> REPLACE

# An example of *SEARCH/REPLACE* edit:
REPAIR_INSTRUCT = '''
Now, you need to generate patches to resolve the issue. Please ensure that your patch does not disrupt the original functionality of the code.
You should generate *SEARCH/REPLACE* format patches to fix the issue.
Every *SEARCH/REPLACE* edit must use this format:
```pythony
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

A final json reply example:
```json
{
  "search_replace_edits": [
    "### A/B.py\\n<<<<<<< SEARCH\n       def foo():\\n=======\\n    def bar():\\n>>>>>>> REPLACE\\n",
    "### A/B.py\\n<<<<<<< SEARCH\n       x = x + 1\\n=======\\n    x = x - 1\\n>>>>>>> REPLACE\\n",
}
```

'''

REGENERATION_INSTRUCT = '''
In the last round, you have tried to generate a patch to resolve the issue.
This is the last round output:

## LAST ROUND OUTPUT
<LAST_ROUND_OUTPUT>
{history}
</LAST_ROUND_OUTPUT>



Oops! It looks like the reviewer had some concerns about your latest patch.
This is the program output after applying your latest patch:
## PATCHED OUTPUT
```
{patched_output}
```


A reviewer has provided the following feedback:

## REVIEWER FEEDBACK
<REVIEWER_FEEDBACK>
{reviewer_feedback}
</REVIEWER_FEEDBACK>



Now, please first think about whether there might be an issue with your previous patch — or if perhaps the reviewer misunderstood something
Then, regenerate the patch to fix the issue, following the same format as before.
'''


PATCH_SELECTION_AGENT_SYSTEM_MSG = 'You are a pull request reviewer. You need to choose the one PR from multiple that actually will resolve the given issue.'

PATCH_SELECTION_HEAD = '''
Here is the issue in the **{project}** project:
## ISSUE
<ISSUE>
{issue}
</ISSUE>

To resolve the issue, several repair agents have generated their patches.
Your task is to determine which patch is the best one to fix the issue.

The following are the patch outputs for each repair agent:
{patches}

'''

PATCH_SELECTION_INSTRUCT = '''
Now, please first analyse the issue as well as its root cause, and think about which patch is the best one to fix the issue.

Then, please provide the patch you think is the best by providing its patch ID in the following format:
Best Patch: `{PATCH_ID}`
'''
