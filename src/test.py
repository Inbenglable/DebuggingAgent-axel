import ast
from typing import List, Dict, Any
import textwrap

def extract_function_call(text: str) -> List[Dict[str, Any]]:
    """
    Extracts specific function calls and their arguments from the given text.

    Returns a list of dicts like:
    {
        "function": "search_method_in_file",
        "args": ["FILE_PATH", "METHOD_NAME"]
    }
    """
    function_names = {"search_method_in_file", "search_class_in_file", "search_code_in_file"}
    results = []
    text = '\n'.join(line.strip() for line in text.splitlines() if line.strip())  # Remove empty lines
    # Wrap the code in a dummy function to make it parsable
    code = f"def _():\n{textwrap.indent(text, '    ')}"
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in function_names:
                args = []
                for arg in node.args:
                    if isinstance(arg, ast.Constant):  # For Python 3.8+
                        args.append(arg.value)
                    elif isinstance(arg, ast.Str):  # For Python <3.8
                        args.append(arg.s)
                    else:
                        args.append(ast.unparse(arg))  # fallback
                results.append({
                    "function": func_name,
                    "args": args
                })
    return results


text = '''
search_method_in_file("service/engine.py", "Engine.run")
search_code_in_file("core/utils.py", "print(\\"debug\\")")
search_code_in_file("core/utils.py", "print(\\"debug\\")")
search_class_in_file("models/user.py", "User")
'''

import pprint
try:
    calls = extract_function_call(text)
    for call in calls:
        pprint.pprint(call)
except Exception:
    print(text)
