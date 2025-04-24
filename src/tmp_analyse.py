import os
import json


def get_resolved_bugs(root_dir):
    resolved_bugs= []
    non_resolved_bugs = []

    for dire in os.listdir(root_dir):
        if dire.endswith(".json"):
            continue
        for file in os.listdir(os.path.join(root_dir, dire)):
            if file.endswith(".json"):
                with open(os.path.join(root_dir, dire, file), "r") as f:
                    data = json.load(f)
                    if data["status"] == "RESOLVED_FULL":
                        resolved_bugs.append(dire)

    for bug in os.listdir(root_dir):
        if bug.endswith(".json"):
            continue
        if bug not in resolved_bugs:
            non_resolved_bugs.append(bug)

    return resolved_bugs

# root_dir = '/data/swe-fl/SRC/DebuggingAgent'
# all_resolved_bugs = set()
# for dire in os.listdir(root_dir):
#     if os.path.isdir(os.path.join(root_dir, dire)) and dire.startswith("exp_"):
#         resolved_bugs = get_resolved_bugs(os.path.join(root_dir, dire))
#         all_resolved_bugs.update(set(resolved_bugs))

# with open("all_resolved_bugs.json", "w") as f:
#     json.dump(list(all_resolved_bugs), f, indent=4)


conflict_bugs = []
root_dir = '/data/swe-fl/SRC/DebuggingAgent/exp/exp_0423'
for dire in os.listdir(root_dir):
    if dire.endswith(".json"):
        continue
    for file in os.listdir(os.path.join(root_dir, dire)):
        if file.endswith(".json"):
            with open(os.path.join(root_dir, dire, file), "r") as f:
                data = json.load(f)
                if (data["status"] == "RESOLVED_FULL" and data["llm_review"] == False)or (data["status"] != "RESOLVED_FULL" and data["llm_review"] == True):
                    conflict_bugs.append(dire)

with open("conflict_bugs.json", "w") as f:
    json.dump(list(set(conflict_bugs)), f, indent=4)