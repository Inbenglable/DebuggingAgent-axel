# import os
# import json

# resolved_bugs= []
# non_resolved_bugs = []
# root_dir = '/data/swe-fl/SRC/DebuggingAgent/exp_0420'

# for dire in os.listdir(root_dir):
#     if dire.endswith(".json"):
#         continue
#     for file in os.listdir(os.path.join(root_dir, dire)):
#         if file.endswith(".json"):
#             with open(os.path.join(root_dir, dire, file), "r") as f:
#                 data = json.load(f)
#                 if data["status"] == "RESOLVED_FULL":
#                     resolved_bugs.append(dire)

# for bug in os.listdir(root_dir):
#     if bug.endswith(".json"):
#         continue
#     if bug not in resolved_bugs:
#         non_resolved_bugs.append(bug)

# with open("resolved_bugs.json", "w") as f:
#     json.dump(resolved_bugs, f, indent=4)

# with open("non_resolved_bugs.json", "w") as f:
#     json.dump(non_resolved_bugs, f, indent=4)


import re
def judge_review_reply(response: str):
    pattern = r"\*{0,2}([Ii]ssue [Rr]esolved)\*{0,2}:\s*`?([^:`\n\*]+)`?"
    if match := re.search(pattern, response):
        ans = match.group(2).strip().lower()
        print(ans)
        if ans == 'true' or ans == 'false':
            return True
    return False
        
with open('tmp.txt', 'r') as f:
    content = f.read()
    
print(judge_review_reply(content))