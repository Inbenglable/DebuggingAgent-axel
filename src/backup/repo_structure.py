import xml.etree.ElementTree as ET
import os

def extract_file_paths(xml_file):
    """
    Parse the given XML file to extract all class file paths from the 'filename' attribute.
    """
    tree = ET.parse(xml_file)
    root = tree.getroot()

    file_paths = set()
    for package in root.findall(".//package"):
        for class_elem in package.findall(".//class"):
            filename = class_elem.get('filename')
            if filename:
                file_paths.add(filename)
    
    return file_paths

def build_file_tree(file_paths):
    """
    Build a hierarchical file tree structure from a list of file paths.
    """
    file_tree = {}
    
    for path in file_paths:
        parts = path.split(os.sep)  # Split the path by directories
        d = file_tree
        for part in parts:
            d = d.setdefault(part, {})  # Create nested dictionary for each part
    
    return file_tree

def file_tree_to_str(file_tree, indent=0):
    """
    Convert the file tree structure to a string representation.
    """
    result = ""
    for name, subtree in file_tree.items():
        result += '  ' * indent + name + '\n'  # Add the current name with indentation
        if isinstance(subtree, dict):  # If the subtree is a directory
            result += file_tree_to_str(subtree, indent + 1)  # Recursively add the children
    return result

def get_file_tree_str(xml_file):
    """
    Extract file paths from the XML and return a file tree structure as a string.
    """
    # Step 1: Extract file paths from XML
    file_paths = extract_file_paths(xml_file)

    # Step 2: Build file tree from file paths
    file_tree = build_file_tree(file_paths)

    # Step 3: Convert the file tree to string
    return file_tree_to_str(file_tree)

def get_covered_lines(xml_file, target_filename):
    """
    Given a filename, retrieve all covered lines and their line numbers.
    Display them similar to the 'cat -n' command.
    
    Parameters:
    - xml_file: Path to the coverage XML file.
    - target_filename: The filename to retrieve covered lines for.
    
    Returns:
    - A string with covered lines prefixed by their line numbers.
    """
    tree = ET.parse(xml_file)
    root = tree.getroot()

    # Extract source directory
    source = root.find(".//sources/source")
    if source is not None:
        source_dir = source.text
    else:
        source_dir = ""

    covered_lines = set()

    # Iterate through all classes to find the target file
    for package in root.findall(".//package"):
        for class_elem in package.findall(".//class"):
            filename = class_elem.get('filename')
            if filename == target_filename:
                for line in class_elem.findall(".//line"):
                    hits = int(line.get('hits', '0'))
                    if hits > 0:
                        line_number = int(line.get('number'))
                        covered_lines.add(line_number)
                break  # Assuming filenames are unique

    if not covered_lines:
        return f"No covered lines found for file: {target_filename}"

    # Construct full file path
    file_path = os.path.join(source_dir, target_filename)

    if not os.path.isfile(file_path):
        return f"Source file not found: {file_path}"

    # Read the source file and collect covered lines
    covered_content = []
    with open(file_path, 'r') as f:
        for idx, line in enumerate(f, start=1):
            if idx in covered_lines:
                covered_content.append(f"{idx}\t{line.rstrip()}")

    return "\n".join(covered_content)

# Example usage:
if __name__ == "__main__":
    coverage_xml = "/data/SWE/SRC/approach/tmp/testbed/astropy__astropy-14182/astropy__astropy__5.1/coverage.xml"  # Path to your coverage XML file

    # Display the file tree
    print("File Tree:")
    print(get_file_tree_str(coverage_xml))

    # Get covered lines for a specific file
    filename = "astropy/io/ascii/ui.py"  # Replace with your target filename
    print(f"\nCovered lines in {filename}:")
    print(get_covered_lines(coverage_xml, filename))






# from rich import print
# from rich.tree import Tree
# import os
# from rich.console import Console
# from rich.table import Table
# import sys
# 
# def should_exclude(entry):
#     """
#     Filter function to determine whether a file or folder should be included in the tree.

#     :param entry: Name of the file or folder.
#     :return: True if the entry should be included, False otherwise.
#     """
#     # Rule 1: Exclude hidden files and folders that start with a dot.
#     if entry.startswith('.'):
#         return False
    
#     # You can add more filtering rules here. For example:
#     # Rule 2: Exclude specific file types, such as .log files.
#     # if entry.endswith('.log'):
#     #     return False

#     return True

# def add_tree_nodes(tree, path, current_depth, max_depth):
#     """
#     Recursively adds nodes to the tree until the maximum depth is reached,
#     applying the filtering rules.

#     :param tree: rich.tree.Tree object representing the current tree node.
#     :param path: Path of the current directory.
#     :param current_depth: Current depth in the tree.
#     :param max_depth: Maximum depth to generate the tree.
#     """
#     if current_depth > max_depth:
#         tree.add("[italic]...[/italic]")  # Indicates that there are more items not displayed.
#         return
#     try:
#         entries = sorted(os.listdir(path))
#     except PermissionError:
#         tree.add("[red]Permission Denied[/red]")
#         return
#     except FileNotFoundError:
#         tree.add("[red]Path Not Found[/red]")
#         return

#     for entry in entries:
#         if not should_exclude(entry):
#             continue  # Skip entries that do not meet the filtering criteria.

#         full_path = os.path.join(path, entry)
#         if os.path.isdir(full_path):
#             branch = tree.add(f"[bold blue]{entry}/[/bold blue]")
#             add_tree_nodes(branch, full_path, current_depth + 1, max_depth)
#         else:
#             tree.add(entry)


# def generate_tree(path, max_depth=3):
#     """
#     Generates and prints a file tree starting from the specified path.

#     :param path: Root path from which to generate the file tree.
#     :param max_depth: Maximum depth of the tree. Default is 3.
#     """
#     base_name = os.path.basename(os.path.abspath(path))
#     tree = Tree(f"[green]{base_name}/[/green]")
#     add_tree_nodes(tree, path, current_depth=1, max_depth=max_depth)
#     print(tree)


# def cat_n_rich(file_path, padding=6):
#     if not os.path.isfile(file_path):
#         print(f"Error: '{file_path}' not exist.", file=sys.stderr)
#         sys.exit(1)

#     console = Console()
#     table = Table(show_header=False, show_edge=False, box=None)
#     table.add_column("Line", justify="right", width=padding, style="cyan")
#     table.add_column("Content", style="white")

#     try:
#         with open(file_path, 'r', encoding='utf-8') as file:
#             for idx, line in enumerate(file, start=1):
#                 table.add_row(str(idx), line.rstrip())
#         console.print(table)
#     except PermissionError:
#         console.print(f"[red]PermissionError: '{file_path}' [/red]", style="red")
#         sys.exit(1)
#     except Exception as e:
#         console.print(f"[red]An error occurred: {e}[/red]", style="red")
#         sys.exit(1)

# # Example Usage
# generate_tree('/data/SWE/DATA/swe-instance/astropy__astropy-12907', max_depth=2)
# cat_n_rich('/data/SWE/SRC/approach/src/log.py')
