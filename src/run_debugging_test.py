import os
import runpy
import json
import argparse
import traceback
import dbgsnooper  

def debugging_test_execution_wrapper(test_path, file_scope_dict, depth=1, loop=None):
    test_path = os.path.abspath(test_path)
    @dbgsnooper.snoop(file_scope_dict=file_scope_dict, depth=depth, loop=loop)
    def wrapped_execute():
        runpy.run_path(test_path, run_name="__main__")
    try:
        wrapped_execute()
    except Exception as e:
        print(f"Error occurred during script execution:{e}")
        traceback.print_exc()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-path", required=True)
    parser.add_argument("--file-scope-dict", required=True)
    parser.add_argument("--depth", type=int, default=1)
    parser.add_argument("--loop", type=int, default=None)
    args = parser.parse_args()
    

    file_scope_dict = json.loads(args.file_scope_dict)
    debugging_test_execution_wrapper(args.test_path, file_scope_dict, args.depth, args.loop)

    # debugging_test_execution_wrapper('/data/SWE/SRC/approach/tmp/testbed/astropy__astropy-12907/astropy__astropy__4.3/debugging_test.py'\
    # , {'/data/SWE/SRC/approach/tmp/testbed/astropy__astropy-12907/astropy__astropy__4.3/astropy/modeling/core.py': (57, 57)}, 1, 0)