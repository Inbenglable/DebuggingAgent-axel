import os
from pathlib import Path
import libcst as cst
from libcst import CSTTransformer, ClassDef, FunctionDef, Decorator, Name, Attribute, Call, Arg, Import, ImportFrom, SimpleStatementLine
from typing import List, Union


class DecoratorModifier(cst.CSTTransformer):
    """
    CST Transformer to add or remove the pysnooper.snoop decorator
    to/from specified functions or classes, and ensure necessary imports.
    """

    def __init__(self, target_names: List[str], action: str = 'add',
                 decorator_name: str = 'pysnooper', decorator_attr: str = 'snoop',
                 import_module: str = 'pysnooper'):
        """
        Initialize the transformer.

        :param target_names: List of function or class names to target.
        :param action: 'add' to add decorator, 'remove' to remove decorator.
        :param decorator_name: Module name where the decorator resides.
        :param decorator_attr: The attribute name of the decorator (e.g., 'snoop').
        :param import_module: The module to import (default: 'pysnooper').
        """
        self.target_names = set(target_names)
        self.action = action.lower()
        self.decorator_name = decorator_name
        self.decorator_attr = decorator_attr
        self.import_module = import_module
        self.has_import = False
        self.import_added = False

    def visit_Import(self, node: Import) -> None:
        """
        Check if the import_module is already imported.

        :param node: Import node.
        """
        for alias in node.names:
            if alias.evaluated_name == self.import_module:
                self.has_import = True

    def visit_ImportFrom(self, node: ImportFrom) -> None:
        """
        Check if the import_module is already imported.

        :param node: ImportFrom node.
        """
        if node.module and node.module.value == self.import_module:
            self.has_import = True

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:
        """
        Add import statement at the module level if needed.

        :param original_node: Original module node.
        :param updated_node: Updated module node.
        :return: Possibly modified module node.
        """
        if self.action == 'add' and not self.has_import and not self.import_added:
            pysnooper_import = SimpleStatementLine(
                body=[
                    cst.Import(names=[cst.ImportAlias(name=cst.Name(self.import_module))])
                ]
            )
            # Insert after existing imports
            new_body = []
            insert_pos = 0
            for i, stmt in enumerate(updated_node.body):
                new_body.append(stmt)
                if isinstance(stmt, (cst.Import, cst.ImportFrom)):
                    insert_pos = i + 1
            new_body.insert(insert_pos, pysnooper_import)
            self.import_added = True
            return updated_node.with_changes(body=new_body)
        return updated_node

    def leave_FunctionDef(self, original_node: FunctionDef, updated_node: FunctionDef) -> FunctionDef:
        """
        Modify decorators of function definitions.

        :param original_node: Original FunctionDef node.
        :param updated_node: Updated FunctionDef node.
        :return: Possibly modified FunctionDef node.
        """
        if original_node.name.value in self.target_names:
            return self._modify_decorators(updated_node)
        return updated_node

    def leave_ClassDef(self, original_node: ClassDef, updated_node: ClassDef) -> ClassDef:
        """
        Modify decorators of class definitions.

        :param original_node: Original ClassDef node.
        :param updated_node: Updated ClassDef node.
        :return: Possibly modified ClassDef node.
        """
        if original_node.name.value in self.target_names:
            return self._modify_decorators(updated_node)
        return updated_node

    def _modify_decorators(self, node: Union[FunctionDef, ClassDef]) -> Union[FunctionDef, ClassDef]:
        """
        Add or remove decorators based on the action.

        :param node: FunctionDef or ClassDef node.
        :return: Possibly modified node.
        """
        decorators = list(node.decorators)

        if self.action == 'add':
            # Check if decorator already exists
            for decorator in decorators:
                if self._is_pysnooper_decorator(decorator.decorator):
                    return node  # Decorator already exists

            # Create new pysnooper.snoop(depth=2, color=False) decorator
            new_decorator = Decorator(
                decorator=cst.Call(
                    func=cst.Attribute(
                        value=cst.Name(self.decorator_name),
                        attr=cst.Name(self.decorator_attr)
                    ),
                    args=[
                        Arg(
                            keyword=cst.Name('depth'),
                            value=cst.Integer('2')
                        ),
                        Arg(
                            keyword=cst.Name('color'),
                            value=cst.Name('False')
                        )
                    ]
                )
            )
            decorators.insert(0, new_decorator)  # Insert at the beginning
            return node.with_changes(decorators=decorators)

        elif self.action == 'remove':
            # Remove all pysnooper.snoop decorators
            decorators = [dec for dec in decorators if not self._is_pysnooper_decorator(dec.decorator)]
            return node.with_changes(decorators=decorators)

        return node

    def _is_pysnooper_decorator(self, decorator: cst.BaseExpression) -> bool:
        """
        Check if the decorator is pysnooper.snoop.

        :param decorator: Decorator expression.
        :return: True if it is pysnooper.snoop, False otherwise.
        """
        if isinstance(decorator, cst.Call):
            func = decorator.func
            if isinstance(func, cst.Attribute):
                if isinstance(func.value, cst.Name):
                    return func.value.value == self.decorator_name and func.attr.value == self.decorator_attr
        return False


def modify_decorators_libcst(source_file_path: Path, target_names: List[str], action: str = 'add',
                             decorator_name: str = 'pysnooper', decorator_attr: str = 'snoop',
                             import_module: str = 'pysnooper') -> None:
    """
    Modify decorators in the source file using libcst.

    :param source_file_path: Path to the source file.
    :param target_names: List of function or class names to modify.
    :param action: 'add' or 'remove'.
    :param decorator_name: Module name where the decorator resides.
    :param decorator_attr: Attribute name of the decorator.
    :param import_module: Module to import.
    """
    if not source_file_path.is_file():
        raise FileNotFoundError(f"Source file not found: {source_file_path}")

    with open(source_file_path, 'r', encoding='utf-8') as file:
        source_code = file.read()

    # Parse the source code into a CST
    module = cst.parse_module(source_code)

    # Initialize the transformer
    transformer = DecoratorModifier(
        target_names=target_names,
        action=action,
        decorator_name=decorator_name,
        decorator_attr=decorator_attr,
        import_module=import_module
    )

    # Apply the transformer
    modified_tree = module.visit(transformer)

    # Get the modified code
    modified_code = modified_tree.code

    # Write the modified code back to the source file
    with open(source_file_path, 'w', encoding='utf-8') as file:
        file.write(modified_code)


# 示例用法
if __name__ == "__main__":
    runtime_info= [
        "astropy/modeling/separable.py:separability_matrix",
        "astropy/modeling/separable.py:_separable"
    ]
    for target in runtime_info:
        try:
            file_path, method = target.split(':')
            abs_file_path = Path(f"/data/SWE/SRC/approach/tmp/testbed/astropy__astropy-12907/astropy__astropy__4.3/{file_path}")
            modify_decorators_libcst(abs_file_path, target_names=[method], action='add')
            # modify_decorators_libcst(abs_file_path, target_names=[method], action='remove')
            print(f"Successfully modified decorators in {abs_file_path} for '{method}'.")
        except Exception as e:
            print(f"Error modifying {target}: {e}")



# import ast
# import astor
# import os
# from functools import cache
# from pathlib import Path
# import pysnooper


# class DecoratorTransformer(ast.NodeTransformer):
#     """
#     AST Node Transformer to add or remove the pysnooper decorator
#     to/from specified functions or classes, and modify its parameters.
#     """

#     def __init__(self, target_names, decorator_name='pysnooper', import_module='pysnooper', action='add'):
#         """
#         Initializes the transformer.

#         :param target_names: List of function or class names to target.
#         :param decorator_name: Name of the decorator to add/remove.
#         :param import_module: Module from which the decorator is imported.
#         :param action: 'add' to add the decorator, 'remove' to remove it.
#         """
#         self.target_names = target_names
#         self.decorator_name = decorator_name
#         self.import_module = import_module
#         self.action = action.lower()
#         self.import_added = False
#         self.import_present = False

#     def visit_Import(self, node):
#         """
#         Visits Import nodes to check if the import_module is already imported.

#         :param node: AST Import node.
#         :return: Unmodified or modified AST node.
#         """
#         for alias in node.names:
#             if alias.name == self.import_module:
#                 self.import_present = True
#         return node

#     def visit_ImportFrom(self, node):
#         """
#         Visits ImportFrom nodes to check if the import_module is already imported.

#         :param node: AST ImportFrom node.
#         :return: Unmodified or modified AST node.
#         """
#         if node.module == self.import_module:
#             self.import_present = True
#         return node

#     def add_import_if_needed(self, tree):
#         """
#         Adds the import statement for the decorator if it's not already present.

#         :param tree: AST tree of the source code.
#         """
#         if not self.import_present and self.action == 'add':
#             # Create a new import statement: import pysnooper
#             new_import = ast.Import(names=[ast.alias(name=self.import_module, asname=None)])
#             insert_pos = 0
#             for idx, node in enumerate(tree.body):
#                 if isinstance(node, (ast.Import, ast.ImportFrom)):
#                     insert_pos = idx + 1
#             tree.body.insert(insert_pos, new_import)
#             self.import_added = True

#     def visit_FunctionDef(self, node):
#         """
#         Visits FunctionDef nodes to add or remove the decorator.

#         :param node: AST FunctionDef node.
#         :return: Modified AST node.
#         """
#         if node.name in self.target_names:
#             if self.action == 'add':
#                 node = self.add_decorator(node)
#             elif self.action == 'remove':
#                 node = self.remove_decorator(node)
#         return node

#     def visit_ClassDef(self, node):
#         """
#         Visits ClassDef nodes to add or remove the decorator.

#         :param node: AST ClassDef node.
#         :return: Modified AST node.
#         """
#         if node.name in self.target_names:
#             if self.action == 'add':
#                 node = self.add_decorator(node)
#             elif self.action == 'remove':
#                 node = self.remove_decorator(node)
#         return node

#     def add_decorator(self, node):
#         """
#         Adds the pysnooper decorator with specified parameters to the node.

#         :param node: AST FunctionDef or ClassDef node.
#         :return: Modified AST node.
#         """
#         # Check if the decorator already exists
#         has_pysnooper = False
#         for dec in node.decorator_list:
#             if isinstance(dec, ast.Call) and \
#                isinstance(dec.func, ast.Attribute) and \
#                dec.func.attr == 'snoop' and \
#                isinstance(dec.func.value, ast.Name) and \
#                dec.func.value.id == self.decorator_name:
#                 has_pysnooper = True
#                 break

#         if not has_pysnooper:
#             # Create the decorator: pysnooper.snoop(depth=2, color=False)
#             new_decorator = ast.Call(
#                 func=ast.Attribute(
#                     value=ast.Name(id=self.decorator_name, ctx=ast.Load()),
#                     attr='snoop',
#                     ctx=ast.Load()
#                 ),
#                 args=[],
#                 keywords=[
#                     ast.keyword(arg='depth', value=ast.Constant(value=2)),
#                     ast.keyword(arg='color', value=ast.Constant(value=False))
#                 ]
#             )
#             # Insert the decorator at the beginning of the decorator list
#             node.decorator_list.insert(0, new_decorator)
#         return node

#     def remove_decorator(self, node):
#         """
#         Removes the pysnooper decorator from the node if it exists.

#         :param node: AST FunctionDef or ClassDef node.
#         :return: Modified AST node.
#         """
#         new_decorators = []
#         for dec in node.decorator_list:
#             # Check if the decorator is pysnooper.snoop
#             if isinstance(dec, ast.Call) and \
#                isinstance(dec.func, ast.Attribute) and \
#                dec.func.attr == 'snoop' and \
#                isinstance(dec.func.value, ast.Name) and \
#                dec.func.value.id == self.decorator_name:
#                 # Skip adding this decorator to remove it
#                 continue
#             new_decorators.append(dec)
#         node.decorator_list = new_decorators
#         return node


# def modify_decorators(source_file_path, target_names, action='add',
#                       decorator_name='pysnooper', import_module='pysnooper'):
#     """
#     Modifies the decorators in the specified source file by adding or removing
#     the pysnooper decorator from the target functions or classes.

#     :param source_file_path: Path to the source Python file.
#     :param target_names: List of function or class names to target.
#     :param action: 'add' to add decorators, 'remove' to remove decorators.
#     :param decorator_name: Name of the decorator (default: 'pysnooper').
#     :param import_module: Module from which the decorator is imported (default: 'pysnooper').
#     :raises FileNotFoundError: If the source file does not exist.
#     """
#     if not os.path.isfile(source_file_path):
#         raise FileNotFoundError(f"Source file not found: {source_file_path}")

#     with open(source_file_path, 'r', encoding='utf-8') as file:
#         source_code = file.read()

#     # Parse the source code into an AST
#     tree = ast.parse(source_code)

#     # Initialize the transformer
#     transformer = DecoratorTransformer(
#         target_names=target_names,
#         decorator_name=decorator_name,
#         import_module=import_module,
#         action=action
#     )

#     # Apply the transformer to the AST
#     transformer.visit(tree)

#     # Add import statement if needed
#     transformer.add_import_if_needed(tree)

#     # Fix any missing locations in the AST
#     ast.fix_missing_locations(tree)

#     # Convert the modified AST back to source code
#     modified_code = astor.to_source(tree)

#     # Write the modified code back to the source file
#     with open(source_file_path, 'w', encoding='utf-8') as file:
#         file.write(modified_code)


# # Example Usage
# if __name__ == "__main__":
#     runtime_info = [
#         "astropy/modeling/separable.py:separability_matrix",
#     ]
#     for target in runtime_info:
#         file_path, method = target.split(':')
#         abs_file_path = Path(f"/data/SWE/SRC/approach/tmp/testbed/astropy__astropy-12907/astropy__astropy__4.3/{file_path}")
#         modify_decorators(abs_file_path, method)
#     # # Path to the source file you want to modify
#     # source_path = 'example.py'

#     # # List of function or class names to target
#     # targets = ['target_function', 'TargetClass']

#     # # To add the pysnooper decorator with depth=2 and color=False
#     # modify_decorators(
#     #     source_file_path=source_path,
#     #     target_names=targets,
#     #     action='add'
#     # )

#     # To remove the pysnooper decorator from the specified targets
#     # modify_decorators(
#     #     source_file_path=source_path,
#     #     target_names=targets,
#     #     action='remove'
#     # )


# # if __name__ == '__main__':
# #     source_file = (
# #         '/data/SWE/DATA/swe-checkout/gold/astropy__astropy-12907/astropy__astropy__4.3/astropy/modeling/separable.py'
# #     )
# #     try:
# #         add_pysnooper_decotator(source_file)
# #     except Exception as e:
# #         print(f"Error modifying source code: {e}")
