import json
import ast
import re
from functools import cache
from pathlib import Path

@cache
def method_and_class_ranges_in_file(file: str):
    """
    Find the ranges of all methods and classes in a Python file.

    Result key is the method or class name, value is (start_line, end_line), inclusive.
    """
    class MethodAndClassRangeFinder(ast.NodeVisitor):
        def __init__(self):
            self.range_map = {}
            self.class_stack = []

        def calc_method_id(self, method_name: str) -> str:
            """Calculate the full method or function name, including its class if applicable."""
            full_class_name = ".".join(self.class_stack)
            return full_class_name + '.' + method_name if full_class_name else method_name

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            """Handle class definitions and record their start and end line numbers."""
            self.class_stack.append(node.name)
            full_class_name = ".".join(self.class_stack)
            self.range_map[full_class_name] = {
                'type': 'class',
                'start_line': node.lineno,
                'end_line': node.end_lineno
            }
            super().generic_visit(node)
            self.class_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            """Handle synchronous function definitions."""
            method_id = self.calc_method_id(node.name)
            assert node.end_lineno
            self.range_map[method_id] = {
                'type': 'method',
                'start_line': node.lineno,
                'end_line': node.end_lineno
            }

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            """Handle asynchronous function definitions."""
            method_id = self.calc_method_id(node.name)
            assert node.end_lineno
            self.range_map[method_id] = {
                'type': 'method',
                'start_line': node.lineno,
                'end_line': node.end_lineno
            }

    finder = MethodAndClassRangeFinder()

    if not Path(file).exists():
        print(f"File {file} does not exist")
        return {}
    source = Path(file).read_text()

    try:
        tree = ast.parse(source, file)
    except SyntaxError:
        print(f"SyntaxError in {file}")
        return {}

    finder.visit(tree)

    return finder.range_map

def generate_skeleton(file: str, name: str, enable_line_number: bool = False) -> str:
    """
    Generate the skeleton of a specific class or method with source code line numbers.

    The skeleton replaces 'pass' with '...' and includes the last line of the function.

    Args:
        file (str): The path to the Python file.
        name (str): The full name of the class or method to generate skeleton for.
        enable_line_number (bool): Whether to include line numbers in the skeleton code.

    Returns:
        str: The skeleton code as a string with line numbers.
    """
    code_map = method_and_class_ranges_in_file(file)
    if name not in code_map:
        for map_name in code_map:
            name_last = map_name.split('.')[-1]
            if name == name_last:
                name = map_name
        if name not in code_map:
            raise ValueError(f"No matching class/method found for name: {name} in file: {file}")

    element_info = code_map[name]
    with open(file, 'r') as f:
        lines = f.read().split('\n')

    start = element_info['start_line']
    end = element_info['end_line']

    skeleton = []

    def add_line_number(line: str, line_number: int):
        """Helper function to add line numbers to the code if required"""
        if enable_line_number:
            return f"{line_number:6}\t{line}"
        return line

    inside_class = False
    inside_function = False


    for i, line in enumerate(lines[start - 1:end]):
        stripped_line = line.strip()
        curr_indent = len(line) - len(line.lstrip())
        if inside_function:
            if curr_indent > function_indent or stripped_line == "":
                continue
            else:
                inside_function = False
                if not enable_line_number:
                    skeleton.append('')
        
        if stripped_line.startswith("class "):
            # Handle class definition, keep the class header and class-level code
            inside_class = True
            class_indent = curr_indent
            skeleton.append(add_line_number(line, i + start))

        elif inside_class and stripped_line.startswith("def "):
            # If inside a class, and it's a function definition, only keep the function header
            inside_function = True
            function_indent = curr_indent
            # Add the function header (with original indent)
            skeleton.append(add_line_number(line, i + start))

            # Replace the body of the function with `...` and keep the same indentation level
            if enable_line_number:
                skeleton.append(f"{' ' * (function_indent + 10)}...")
            else:
                skeleton.append(f"{' ' * (function_indent + 4)}...")


        elif inside_class:
            # Keep other lines in the class (e.g., class variables or assignments)
            skeleton.append(add_line_number(line, i + start))


    return '\n'.join(skeleton)

def get_surrounding_lines(file_name: str, code_snippet: str):
    """
    Find all occurrences of a code snippet in the file and return surrounding lines.

    Returns:
        List of tuples: [(code_str, start_line_number, end_line_number), ...]
    """
    code_snippet = code_snippet.strip()

    with open(file_name, 'r') as file:
        file_content = file.read()
        lines = file_content.splitlines()

    results = []
    snippet_len = len(code_snippet)
    start_pos = 0

    while True:
        # Look for next occurrence of the snippet
        start_index = file_content.find(code_snippet, start_pos)
        if start_index == -1:
            break

        # Find the line numbers based on newline counts
        snippet_start_line = file_content.count('\n', 0, start_index)
        snippet_end_index = start_index + snippet_len
        snippet_end_line = file_content.count('\n', 0, snippet_end_index)

        # Get up to 3 lines before and after
        start_line = max(snippet_start_line - 3, 0)
        end_line = min(snippet_end_line + 3, len(lines) - 1)

        snippet_lines = lines[start_line:end_line + 1]
        snippet_block = '\n'.join(snippet_lines)

        results.append((snippet_block, start_line + 1, end_line + 1))  # +1 for 1-based line numbers

        # Move search forward to avoid infinite loop
        start_pos = snippet_end_index

    return results




def retrieve_code_element(file: str, name: str, element_type : str, enable_line_number: bool = False):

    result = []
    retrieved_elements = {}
    try:
        with open(file, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        raise FileNotFoundError(f"File {file} not found.")
    if element_type == 'scope':
        line_range_match = re.match(r'^(\d+)-(\d+)$', name)

        if line_range_match:
            start = int(line_range_match.group(1))
            end = int(line_range_match.group(2))
            
            if start > end:
                raise ValueError(f"Invalid line range: start ({start}) is greater than end ({end})")
            
            total_lines = len(lines)
            if start < 1 or end > total_lines:
                raise ValueError(f"Line range {start}-{end} is out of bounds for file {file} with {total_lines} lines.")


            selected_lines = lines[start - 1:end]
            

            numbered_code_lines = [
                f"{i:6}\t{line}" for i, line in enumerate(selected_lines, start=start)
            ]
            
            retrieved_elements['name'] = f"Lines {start}-{end}"
            retrieved_elements['path'] = file
            retrieved_elements['type'] = 'line_range'
            retrieved_elements['start_line'] = start
            retrieved_elements['end_line'] = end
            retrieved_elements['code'] = ''.join(numbered_code_lines)
        else:
            raise ValueError(f"Invalid line range format: {name}. Expected format is 'start-end'.")
        
        return [retrieved_elements]

    elif element_type == 'method' or element_type == 'class':
        code_map = method_and_class_ranges_in_file(file)
        candidate_names = []
        if name not in code_map:
            for map_name in code_map:
                map_name_last = map_name.split('.')[-1]
                name = name.split('.')[-1]
                if name == map_name_last:
                    candidate_names.append(map_name)
            if len(candidate_names) == 0:
                raise ValueError(f"No matching {element_type} found for name: {name} in file: {file}")
        else:
            candidate_names.append(name)

        for name in candidate_names:
            element_info = code_map[name]

            start = element_info['start_line']
            end = element_info['end_line']

            retrieved_elements['name'] = name

            if element_type == 'class':
                skeleton_code = generate_skeleton(file, name, enable_line_number)
                retrieved_elements['code'] = skeleton_code
            else:
                selected_lines = lines[start - 1:end]
                if enable_line_number:
                    returned_code_lines = [
                        f"{i:6}\t{line}" for i, line in enumerate(selected_lines, start=start)
                    ]
                else:
                    returned_code_lines = selected_lines
                retrieved_elements['code'] = ''.join(returned_code_lines)
                
            retrieved_elements['path'] = file
            retrieved_elements['type'] = element_info['type']
            retrieved_elements['start_line'] = start
            retrieved_elements['end_line'] = end
            
            result.append(retrieved_elements)

        return result
    elif element_type == 'code_snippet':
        retrieve_results = get_surrounding_lines(file, name)
        if len(retrieve_results) == 0:
            raise ValueError(f"Code snippet '{name}' not found in file '{file}'.")
        for retrieve_result in retrieve_results:
            code = retrieve_result[0]
            start_line = retrieve_result[1]
            end_line = retrieve_result[2]
             
            retrieved_elements['name'] = 'code_snippet'
            retrieved_elements['path'] = file
            retrieved_elements['type'] = 'code_snippet'
            retrieved_elements['start_line'] = start_line
            retrieved_elements['end_line'] = end_line
            retrieved_elements['code'] = code
            result.append(retrieved_elements)
        return result


if __name__ == '__main__':
    review_src = [
        # "astropy/modeling/separable.py:separability_matrix",
        # "astropy/modeling/separable.py:_separable",
        "astropy/modeling/core.py:CompoundModel"
        # "astropy/modeling/separable.py:66-102"
    ]
    for src in review_src:
        file_path, method = src.split(':')
        abs_file_path = Path(f"/data/SWE/SRC/approach/tmp/testbed/astropy__astropy-12907/astropy__astropy__4.3/{file_path}")
        # 设置 skeleton=True 以生成骨架
        result = retrieve_code_element(abs_file_path, method, skeleton=True)[0]
        if 'code' in result:
            print(result['code'])
        if 'name' in result:
            print(result['name'])

        else:
            print("No code retrieved.")

# print(method_and_class_ranges_in_file('/data/swe-fl/TMP/testbed/scikit-learn__scikit-learn-14894/sklearn/svm/libsvm_sparse.pyx'))