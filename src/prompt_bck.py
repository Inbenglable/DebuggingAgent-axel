# TODO: maybe we do not need advanced usage?
PYSNOOPER_INTRO = '''

You can analyze key variables in the reproducible tests using `pysnooper` (which is already installed). Below is an introduction to using `pysnooper`:

### Using the `@pysnooper.snoop()` Decorator

```python
import pysnooper

@pysnooper.snoop()
def number_to_bits(number):
    if number:
        bits = []
        while number:
            number, remainder = divmod(number, 2)
            bits.insert(0, remainder)
        return bits
    else:
        return [0]

number_to_bits(6)

```

**Output:**

```
Starting var:.. number = 6
call         5 def number_to_bits(number):
line         6     if number:
line         7         bits = []
New var:....... bits = []
line         8         while number:
line         9             number, remainder = divmod(number, 2)
...
line         8         while number:
line        11         return bits
return      11         return bits
Return value:.. [1, 1, 0]
Elapsed time: 00:00:00.001163

```

### Using a `with` Block for Specific Code Sections

```python
import pysnooper
import random

def foo():
    lst = []
    for i in range(10):
        lst.append(random.randrange(1, 1000))

    with pysnooper.snoop():
        lower = min(lst)
        upper = max(lst)
        mid = (lower + upper) / 2
        print(lower, mid, upper)

foo()

```

**Output:**

```
New var:....... i = 9
New var:....... lst = [681, 267, 74, 832, 284, 678, ...]
line        10         lower = min(lst)
New var:....... lower = 74
line        11         upper = max(lst)
New var:....... upper = 832
line        12         mid = (lower + upper) / 2
74 453.0 832
New var:....... mid = 453.0
line        13         print(lower, mid, upper)
Elapsed time: 00:00:00.000344

```

### Features

- **Watch Expressions Not Limited to Local Variables:**
    
    ```python
    @pysnooper.snoop(watch=('foo.bar', 'self.x["whatever"]'))
    
    ```
    
- **Trace Called Functions:**
    
    ```python
    @pysnooper.snoop(depth=2)
    
    ```
    
- **Expand Values with `watch_explode`:**
    
    ```python
    @pysnooper.snoop(watch_explode=('foo', 'self'))
    
    ```
    
    Automatically expands based on the object's class. You can specify:
    
    ```python
    import pysnooper
    
    @pysnooper.snoop(watch=(
        pysnooper.Attrs('x'),         # Attributes
        pysnooper.Keys('y'),          # Dictionary items
        pysnooper.Indices('z'),       # List/Tuple items
    ))
    
    ```
    
- **Exclude Specific Keys/Attributes/Indices:**
    
    ```python
    pysnooper.Attrs('x', exclude=('_foo', '_bar'))
    
    ```

    
- **Decorate Generators and Classes:**
    
    ```python
    @pysnooper.snoop
    def generator_func():
        yield 1
        yield 2
    
    ```
    
    Decorating a class applies `snoop` to all its methods:
    
    ```python
    @pysnooper.snoop
    class MyClass:
        def method(self):
            pass
    
    ```

    
### Recommendations

- **High-Value Runtime Information:**
Using pysnooper.snoop(depth=2, color=False) significantly aids in obtaining valuable runtime information.
- **Limit Excessive Logging:**
To prevent excessive information logging, prefer using the `with pysnooper.snoop():` statement without altering the original syntax.
'''

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

**Debugging Instructions:**

{PYSNOOPER_INTRO}

Follow these steps to resolve the issue:
1. Create a debugging test by modifying the reproduce test. Use `pysnooper.snoop(depth=2, color=False)` to monitor important functions and variables within the reproducible test. This will help you better understand the execution flow. During this process, `pysnooper` will print the paths and details of relevant functions, assisting you in identifying issues and selecting specific code snippets for review.
2. Read the relative source code and using pysnooper to monitor the project code execution unless you identify the root cause.
3. Once you have identified the issue, modify the code accordingly.
4. Rerun reproduce script and confirm that the issue is fixed!

Focus on Step 1: generate a debugging test. At the end of your analysis, provide the specific code in the following **JSON format**.
Note: You should clearly specify the tests you are debugging as much as possible. Minimizing the amount of code will better assist you in analyzing runtime information later.


{{
"debugging_test" : "import ... # Your debugging test code here"
}}

'''



START_DEBUGGING = '''
This is the output from running the debugging test. Next, you need to determine whether the debugging test was executed correctly.

{debugging_test_exec_result}

- **If the debugging test was generated successfully**, proceed to **Step 2**:
  - Select the functions or classes whose source code and dynamic runtime information you wish to examine for deeper debugging.
  - **Before adding code to `runtime_info` for monitoring, ensure you have reviewed the relevant sections. This prevents selecting overly large ranges and generating excessive output.**

- **If the debugging test was not generated successfully**, please regenerate it.

Your analysis should be thorough, and it's acceptable for it to be very detailed.

In **Step 2**, you will perform multiple iterative steps to progressively resolve the issue.

At the end of your analysis, provide the specific information in the following JSON format:


{{
    "is_debugging_test_successfully_generated": "True/False",
    "debugging_test": "YOUR TEST CODE if the previous was not successfully generated",
    "review_src": ["FILE_PATH:METHOD", "FILE_PATH:CLASS", "FILE_PATH:LINE_A-LINE_B"],
    "runtime_info": ["FILE_PATH:METHOD", "FILE_PATH:CLASS"]
}}

Please note that FILE_PATH refers to the path relative to the repository.
Format: `FILE_PATH:LINE_A-LINE_B` -> Example: `src/model.py:10-20`
'''



DEBUGGING_LOOP = '''
This is the output from running the debugging test after adding the `pysnooper` decorator to the observed `runtime_info` list.

{debugging_test_exec_result}

And here is the source code of your `review_src` list. Note that if the review_src is too long, the skeleton of the code will be provided, you can further specify the range of the code you want to review.

{review_src}

**Step 2:** Perform multiple iterative steps to progressively resolve the issue.

It's okay to gather more information and remain in **Step 2** multiple times.

- **Condition to move to Step 3:**
  If you are ready to resolve the issue by precisely modifying the source code (you should at least know the exact line number and have reviewed the original source code), you can move to **Step 3**.
    - Set `move_to_step_3` to 'True'.
    - Set `review_src` and `runtime_info` to NULL.

- **Condition to stay in Step 2:**
  If you are not ready to resolve the issue by modifying the source code, continue with **Step 2** by selecting the functions or classes whose source code and dynamic runtime information you wish to examine for deeper debugging.
    - Set `move_to_step_3` to 'False'.
    - Ensure that you do not repeat the same `review_src` and `runtime_info` lists, as they will be identical to the previous ones and will consume a large amount of context.


**Before adding code to `runtime_info` for monitoring, ensure you have reviewed the relevant sections. This prevents selecting overly large ranges and generating excessive output.**

At the end of your analysis, provide the specific information in the following JSON format:

{{
    "move_to_step_3": "True/False",
    "review_src": ["FILE_PATH:METHOD", "FILE_PATH:CLASS", "FILE_PATH:LINE_A-LINE_B"],
    "runtime_info": ["FILE_PATH:METHOD", "FILE_PATH:CLASS"]
}}
Format: `FILE_PATH:LINE_A-LINE_B` -> Example: `src/model.py:10-20`
'''



MODIFY_SOURCE_CODE = '''
Based on the previous analysis, please provide the specific modified code with minimal changes and indicate the range of modifications. I will replace the code within the specified range with your modified code.

Please pay attention to indentation. The lists of modify_code and modify_range correspond one-to-one.
At the end of your analysis, provide the specific information in the following JSON format:

{{
    "modify_code": ["YOUR MODIFIED CODE", "..."],
    "modify_range": ["FILE_PATH:LINE_A-LINE_B", "..."]
}}
Format: `FILE_PATH:LINE_A-LINE_B` -> Example: `src/model.py:10-20`
'''

TOO_LONG_EXEC_RESULT = '''
The debugging test execution result is too long to display here. Please re-select your `review_src` and `runtime_info` lists to narrow down the scope of your analysis.
'''