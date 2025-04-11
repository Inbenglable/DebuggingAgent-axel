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

def generate_skeleton(file: str, name: str) -> str:
    """
    Generate the skeleton of a specific class or method with source code line numbers.

    The skeleton replaces 'pass' with '...' and includes the last line of the function.

    Args:
        file (str): The path to the Python file.
        name (str): The full name of the class or method to generate skeleton for.

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
            print(f"No matching class/method found for name: {name} in file: {file}")
            return ""

    element_info = code_map[name]
    with open(file, 'r') as f:
        lines = f.readlines()

    start = element_info['start_line']
    end = element_info['end_line']

    element_code = ''.join(lines[start - 1:end])
    try:
        tree = ast.parse(element_code)
    except SyntaxError:
        print(f"SyntaxError while parsing {name} in {file}")
        return ""

    skeleton = []

    class SkeletonVisitor(ast.NodeVisitor):
        def __init__(self, base_line: int, source_lines: list):
            self.base_line = base_line  # Starting line number in the original file
            self.source_lines = source_lines

        def visit_ClassDef(self, node: ast.ClassDef):
            # Construct the class definition line with line number
            bases = ', '.join([base.id for base in node.bases if isinstance(base, ast.Name)])
            class_def = f"class {node.name}({bases}):" if bases else f"class {node.name}:"
            skeleton.append(f"{self.base_line:6}\t{class_def}")
            skeleton.append(f"{self.base_line + 1:6}\t    \"\"\"Class skeleton\"\"\"\n")

            # Visit all methods within the class
            for stmt in node.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.visit(stmt)

        def visit_FunctionDef(self, node: ast.FunctionDef):
            self._process_function(node, async_def=False)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            self._process_function(node, async_def=True)

        def _process_function(self, node, async_def: bool):
            # Determine the absolute line number
            absolute_line = node.lineno + self.base_line - 1
            # Extract function arguments
            args = [arg.arg for arg in node.args.args]
            args_str = ', '.join(args)
            # Determine if the function is async
            def_prefix = "async def" if async_def else "def"
            function_def = f"{def_prefix} {node.name}({args_str})"
            skeleton.append(f"{absolute_line:6}\t    {function_def}")

            if node.body:
                # Extract the last statement from the source code
                last_line_num = node.end_lineno + self.base_line - 1
                last_line = self.source_lines[last_line_num - 1].strip()
                # Add the ellipsis
                skeleton.append(f"{absolute_line + 1:6}\t        ...")

                # Add the last line of the function
                skeleton.append(f"{last_line_num:6}\t        {last_line}\n\n")

    visitor = SkeletonVisitor(base_line=start, source_lines=lines)
    visitor.visit(tree)

    return '\n'.join(skeleton)

# def generate_skeleton(file: str, name: str) -> str:
#     """
#     Generate the skeleton of a specific class or method with source code line numbers.

#     Args:
#         file (str): The path to the Python file.
#         name (str): The full name of the class or method to generate skeleton for.

#     Returns:
#         str: The skeleton code as a string with line numbers.
#     """
#     code_map = method_and_class_ranges_in_file(file)
#     if name not in code_map:
#         print(f"No matching class/method found for name: {name} in file: {file}")
#         return ""

#     element_info = code_map[name]
#     with open(file, 'r') as f:
#         lines = f.readlines()

#     start = element_info['start_line']
#     end = element_info['end_line']

#     element_code = ''.join(lines[start - 1:end])
#     try:
#         tree = ast.parse(element_code)
#     except SyntaxError:
#         print(f"SyntaxError while parsing {name} in {file}")
#         return ""

#     skeleton = []

#     class SkeletonVisitor(ast.NodeVisitor):
#         def __init__(self, base_line: int):
#             self.base_line = base_line  # The starting line number in the original file

#         def visit_ClassDef(self, node: ast.ClassDef):
#             absolute_line = node.lineno + self.base_line - 1
#             # Reconstruct the class definition line with line number prefix
#             bases = ', '.join([base.id if isinstance(base, ast.Name) else "" for base in node.bases])
#             class_def = f"class {node.name}({bases}):" if bases else f"class {node.name}:"
#             skeleton.append(f"{absolute_line:6}\t{class_def}")
#             skeleton.append(f"{absolute_line + 1:6}\t    \"\"\"Class skeleton\"\"\"\n")
#             for stmt in node.body:
#                 if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
#                     self.visit(stmt)
#                 elif isinstance(stmt, ast.Assign):
#                     targets = ', '.join([t.id for t in stmt.targets if isinstance(t, ast.Name)])
#                     value = ast.dump(stmt.value)
#                     skeleton.append(f"{absolute_line + 2:6}\t    {targets} = {value}  # Global variable in class\n")
#             skeleton.append("\n")

#         def visit_FunctionDef(self, node: ast.FunctionDef):
#             absolute_line = node.lineno + self.base_line - 1
#             args = [arg.arg for arg in node.args.args]
#             args_str = ', '.join(args)
#             function_def = f"def {node.name}({args_str}) -> None:"
#             skeleton.append(f"{absolute_line:6}\t    {function_def}")
#             skeleton.append(f"{absolute_line + 1:6}\t        pass\n\n")

#         def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
#             absolute_line = node.lineno + self.base_line - 1
#             args = [arg.arg for arg in node.args.args]
#             args_str = ', '.join(args)
#             function_def = f"async def {node.name}({args_str}) -> None:"
#             skeleton.append(f"{absolute_line:6}\t    {function_def}")
#             skeleton.append(f"{absolute_line + 1:6}\t        pass\n\n")

#         def visit_FunctionDef_top(self, node: ast.FunctionDef):
#             absolute_line = node.lineno + self.base_line - 1
#             args = [arg.arg for arg in node.args.args]
#             args_str = ', '.join(args)
#             function_def = f"def {node.name}({args_str}) -> None:"
#             skeleton.append(f"{absolute_line:6}\t{function_def}")
#             skeleton.append(f"{absolute_line + 1:6}\t    pass\n\n")

#         def visit_Module(self, node: ast.Module):
#             for stmt in node.body:
#                 if isinstance(stmt, ast.ClassDef):
#                     self.visit_ClassDef(stmt)
#                 elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
#                     self.visit_FunctionDef_top(stmt)
#                 elif isinstance(stmt, ast.Assign):
#                     absolute_line = stmt.lineno + self.base_line - 1
#                     targets = ', '.join([t.id for t in stmt.targets if isinstance(t, ast.Name)])
#                     value = ast.dump(stmt.value)
#                     skeleton.append(f"{absolute_line:6}\t{targets} = {value}  # Global variable\n")

#     visitor = SkeletonVisitor(base_line=start)
#     visitor.visit(tree)

#     return '\n'.join(skeleton)




def retrieve_code_and_comment(file: str, name: str, skeleton: bool = False):
    """
    Extract a specific method, class, or line range code along with its line numbers and save it to a JSON file.

    Args:
        file (str): The path to the Python file.
        name (str): The full name of the method or class to extract, or a line range in the format "start-end".
        skeleton (bool): Whether to generate skeleton code instead of full code.
    """
    result = []
    retrieved_elements = {}
    
    line_range_match = re.match(r'^(\d+)-(\d+)$', name)

    with open(file, 'r') as f:
        lines = f.readlines()

    if line_range_match:
        start = int(line_range_match.group(1))
        end = int(line_range_match.group(2))
        
        if start > end:
            print(f"Invalid line range: start ({start}) is greater than end ({end})")
            return []
        
        if not Path(file).exists():
            print(f"File {file} does not exist")
            return []
        
        
        
        total_lines = len(lines)
        if start < 1 or end > total_lines:
            print(f"Line range {start}-{end} is out of bounds for file {file} with {total_lines} lines.")
            return []


        selected_lines = lines[start - 1:end]
        
        if skeleton:
            # Generate skeleton from the selected lines
            selected_code = ''.join(selected_lines)
            try:
                tree = ast.parse(selected_code)
            except SyntaxError:
                print(f"SyntaxError while parsing lines {start}-{end} in {file}")
                return []
            skeleton_code = generate_skeleton(file, name="line_range")
            retrieved_elements['name'] = f"Lines {start}-{end}"
            retrieved_elements['code'] = skeleton_code
        else:
            numbered_code_lines = [
                f"{i:6}\t{line}" for i, line in enumerate(selected_lines, start=start)
            ]
            
            retrieved_elements['name'] = f"Lines {start}-{end}"
            retrieved_elements['path'] = file
            retrieved_elements['type'] = 'line_range'
            retrieved_elements['start_line'] = start
            retrieved_elements['end_line'] = end
            retrieved_elements['code'] = ''.join(numbered_code_lines)
        
        return [retrieved_elements]


    code_map = method_and_class_ranges_in_file(file)
    candidate_names = []
    if name not in code_map:
        for map_name in code_map:
            map_name_last = map_name.split('.')[-1]
            name = name.split('.')[-1]
            if name == map_name_last:
                candidate_names.append(map_name)
        if len(candidate_names) == 0:
            print(f"No matching method/class or valid line range found for name: {name} in file: {file}")
            return []
    else:
        candidate_names.append(name)

    for name in candidate_names:
        element_info = code_map[name]

        start = element_info['start_line']
        end = element_info['end_line']

        retrieved_elements['name'] = name

        if skeleton:
            skeleton_code = generate_skeleton(file, name)
            retrieved_elements['code'] = skeleton_code
        else:
            selected_lines = lines[start - 1:end]
            numbered_code_lines = [
                f"{i:6}\t{line}" for i, line in enumerate(selected_lines, start=start)
            ]
            retrieved_elements['path'] = file
            retrieved_elements['type'] = element_info['type']
            retrieved_elements['start_line'] = start
            retrieved_elements['end_line'] = end
            retrieved_elements['code'] = ''.join(numbered_code_lines)
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
        result = retrieve_code_and_comment(abs_file_path, method, skeleton=True)
        if 'code' in result:
            print(result['code'])
        if 'name' in result:
            print(result['name'])

        else:
            print("No code retrieved.")

# print(method_and_class_ranges_in_file('/data/swe-fl/TMP/testbed/scikit-learn__scikit-learn-14894/sklearn/svm/libsvm_sparse.pyx'))