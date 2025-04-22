import os
import json

resolved_bugs= []
non_resolved_bugs = []
root_dir = '/data/swe-fl/SRC/DebuggingAgent/exp_wo_debugging'

for dire in os.listdir(root_dir):
    for file in os.listdir(os.path.join(root_dir, dire)):
        if file.endswith(".json"):
            with open(os.path.join(root_dir, dire, file), "r") as f:
                data = json.load(f)
                if data["status"] != "RESOLVED_FULL":
                    non_resolved_bugs.append(dire)
                elif data["status"] == "RESOLVED_FULL":
                    resolved_bugs.append(dire)

with open("resolved_bugs.json", "w") as f:
    json.dump(resolved_bugs, f, indent=4)

with open("non_resolved_bugs.json", "w") as f:
    json.dump(non_resolved_bugs, f, indent=4)