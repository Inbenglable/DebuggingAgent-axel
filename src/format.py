import re
import json
import ast
import textwrap

def extract_json_instruction(wrapped_json_str: str) -> str:
    # ```json\nCONTENT\n```
    match_json = re.search(r'```json\s*\n(.*?)\n```', wrapped_json_str, re.DOTALL)
    # log_and_print(match_json)
    if match_json:
        try:
            json_obj = json.loads(match_json.group(1).strip())
            return json_obj
        except json.JSONDecodeError as e:
            raise e
    else:
        raise ValueError("No JSON content found in the response.")


def extract_trace_reply(response: str):

    # 匹配 buggy/observed method，支持带反引号和加粗 Markdown **
    method_pattern = r"\*{0,2}([Bb]uggy [Mm]ethod|[Oo]bserved [Mm]ethod)\*{0,2}:\s*`?([^:`\n]+):([^:`\n]+)`?"

    # 匹配 observed scope，可以是单行或范围，也支持加粗 key
    scope_pattern = r"\*{0,2}[Oo]bserved [Ss]cope\*{0,2}:\s*`?([^:`\n]+):(\d+)(?:-(\d+))?`?"
    
    scope_method_pattern = r"\*{0,2}([Oo]bserved [Ss]cope)\*{0,2}:\s*`?([^:`\n]+):([^:`\n]+)`?"

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
    elif match := re.search(scope_method_pattern, response):
        return {
            "type": 'Observed method',
            "file": match.group(2).strip(),
            "method": match.group(3).strip()
        }
    else:
        raise ValueError("Invalid trace reply format.")
    
    

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


def extract_review_reply(response: str):
    pattern = r"\*{0,2}([Ii]ssue [Rr]esolved)\*{0,2}:\s*`?([^:`\n\*]+)`?"
    if match := re.search(pattern, response):
        if match.group(2).strip().lower() == 'true':
            return True
    return False



def judge_review_reply(response: str):
    pattern = r"\*{0,2}([Ii]ssue [Rr]esolved)\*{0,2}:\s*`?([^:`\n\*]+)`?"
    if match := re.search(pattern, response):
        ans = match.group(2).strip().lower()
        if ans == 'true' or ans == 'false':
            return True
    return False


def judge_ready_generation(response: str):

    pattern = r"\*{0,2}([Rr]eady [Gg]eneration)\*{0,2}:\s*`?([^:`\n]+)`?"

    if match := re.search(pattern, response):
        if match.group(2).strip().lower() == 'true':
            return True

    return False
