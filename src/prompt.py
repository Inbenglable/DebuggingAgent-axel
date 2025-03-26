DEBUGGING_AGENT_SYSTEM_MSG = 'You are a debugging agent tasked with precisely using tools to resolve issues and submit pull requests.'



GEN_DEBUGGING_TEST = '''

You are a debugging agent tasked with precisely using tools to resolve issues and submit pull requests.

**Current Task:**  
Resolve the following issue in the {project} project:

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



START_DEBUGGING = '''
This is the output from running the debugging test. Next, you need to determine whether the debugging test was executed correctly.

<runtime-info>
{debugging_test_exec_result}
</runtime-info>
- **If the debugging test was generated successfully**, proceed to **Step 2**:
  - Select the functions or classes whose source code and dynamic runtime information assist you in deeper debugging.

- **If the debugging test was not generated successfully**, please regenerate it.


Your analysis should be thorough, and it's acceptable for it to be very detailed.

In **Step 2**, you will perform multiple iterative debugging steps to progressively find out the root cause.

- Avoid wasting context:

Iterate through debugging without repeatedly reading the same source code.
Avoid observing identical runtime information multiple times.

- Handling Long Source Code:

A code skeleton will be provided if the source code is too lengthy.
Use the skeleton's line number ranges to identify specific sections to review.

- Adding to runtime_info:

Review relevant code sections before adding them for monitoring.
This ensures you select appropriate ranges and avoid excessive output.


At the end of your analysis, provide the specific information in the following JSON format:


{{
    "is_debugging_test_successfully_generated": "True/False",
    "debugging_test": "YOUR TEST CODE if the previous was not successfully generated",
    "review_src": ["FILE_PATH:METHOD", "FILE_PATH:CLASS", "FILE_PATH:LINE_A-LINE_B"],
    "runtime_info": ["FILE_PATH:LINE_A-LINE_B"]
}}

Please note that FILE_PATH refers to the path relative to the repository.
Format: `FILE_PATH:LINE_A-LINE_B` -> Example: `src/model.py:10-20`.  Note that runtime_info can only accept an exact line number as input. 
'''


# "review_src": ["FILE_PATH:METHOD", "FILE_PATH:CLASS", "FILE_PATH:LINE_A-LINE_B"],
DEBUGGING_LOOP = '''
This is the run time information you want to observe:

<runtime-info>
{debugging_test_exec_result}
</runtime-info>

And here is the source code of your `review_src` list. Note that if the review_src is too long, the skeleton of the code will be provided, you can further specify the range of the code you want to review.

{review_src}

First, analyze the source code and the runtime information you intend to observe.

It's recommended to gather more information and remain in **Step 2** multiple times. 

Note that you should:

- Avoid wasting context:

Iterate through debugging without repeatedly reading the same source code.
Avoid observing identical runtime information multiple times.

- Handling Long Source Code:

A code skeleton will be provided if the source code is too lengthy.
Use the skeleton's line number ranges to identify specific sections to review.

- Adding to runtime_info:

Review relevant code sections before adding them for monitoring.
This ensures you select appropriate ranges and avoid excessive output.


- **Condition to stay in Step 2:**
  If you are not ready to resolve the issue by modifying the source code, continue with **Step 2** by selecting the functions or classes whose source code and dynamic runtime information you wish to examine for deeper debugging.
    - Set `move_to_step_3` to 'False'.
    - Ensure that you do not repeat the same `review_src` and `runtime_info` lists, as they will be identical to the previous ones and will consume a large amount of context.

- **Condition to move to Step 3:**

  You must have completely reviewed the code that needs to be modified before proceeding.
  If you are ready to resolve the issue by precisely modifying the source code, you can move to Step 3.

  - Set move_to_step_3 to True.
  - Set review_src and runtime_info to NULL.



**Before adding code to `runtime_info` for monitoring, ensure you have reviewed the relevant sections. This prevents selecting overly large ranges and generating excessive output.**

At the end of your analysis, provide the specific information in the following JSON format:

{{
    "move_to_step_3": "True/False",
    "review_src": ["FILE_PATH:METHOD", "FILE_PATH:CLASS", "FILE_PATH:LINE_A-LINE_B"],
    "runtime_info": ["FILE_PATH:LINE_A-LINE_B"]
}}
Format: `FILE_PATH:LINE_A-LINE_B` -> Example: `src/model.py:10-20`. Note that runtime_info **can only accept an exact line number as input**. 
'''



MODIFY_SOURCE_CODE = '''
Please ensure that your patch does not disrupt the original functionality of the code.
Generate *SEARCH/REPLACE* patches to fix the issue.

Every *SEARCH/REPLACE* edit must use this format:
1. The file path
2. The start of search block: <<<<<<< SEARCH
3. A contiguous chunk of lines to search for in the existing source code
4. The dividing line: =======
5. The lines to replace into the source code
6. The end of the replace block: >>>>>>> REPLACE

Here is an example:

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
{{
  "search_replace_edits": [
    "edit_1",
    "edit_2"
  ]
}}
'''

# '''
# Based on the previous analysis, please provide the specific modified code with minimal changes and indicate the range of modifications. I will replace the code within the specified range with your modified code.

# Please pay attention to indentation. The lists of modify_code and modify_range correspond one-to-one.
# At the end of your analysis, provide the specific information in the following JSON format:

# {{
#     "modify_code": ["YOUR MODIFIED CODE", "..."],
#     "modify_range": ["FILE_PATH:LINE_A-LINE_B", "..."]
# }}
# Format: `FILE_PATH:LINE_A-LINE_B` -> Example: `src/model.py:10-20`
# '''


TOO_LONG_EXEC_RESULT = '''
The debugging test execution result is too long to display here. Please re-select your `runtime_info` lists to narrow down the scope of your analysis.
'''