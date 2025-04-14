import ast
from typing import List, Dict, Any
import textwrap
from retrieve_src import generate_skeleton, get_surrounding_lines

# text = '''
# search_method_in_file("service/engine.py", "Engine.run")
# search_code_in_file("core/utils.py", "print(\\"debug\\")")
# search_code_in_file("core/utils.py", "print(\\"debug\\")")
# search_class_in_file("models/user.py", "User")
# '''

# print(generate_skeleton('/data/swe-fl/TMP/testbed/astropy__astropy-12907/astropy/modeling/rotations.py','RotateCelestial2Native'))

# print(get_surrounding_lines('/data/swe-fl/TMP/testbed/astropy__astropy-12907/astropy/modeling/rotations.py', ' dtype=np.float64)'))

print(get_surrounding_lines('/data/swe-fl/SRC/DebuggingAgent/src/tmp.txt', '        aszv'))
