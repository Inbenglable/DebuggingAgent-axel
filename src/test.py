import ast
from typing import List, Dict, Any
import textwrap
from retrieve_src import generate_skeleton, get_surrounding_lines
from debugging import extract_function_call
import pprint



# print(generate_skeleton('/data/swe-fl/TMP/testbed/astropy__astropy-12907/astropy/modeling/rotations.py','RotateCelestial2Native'))

# print(get_surrounding_lines('/data/swe-fl/TMP/testbed/astropy__astropy-12907/astropy/modeling/rotations.py', ' dtype=np.float64)'))

with open('tmp.txt', 'r') as f:
    text = f.read()
print(extract_function_call(text)[2]['source_line'])
