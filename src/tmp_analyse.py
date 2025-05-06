import os
import json

def get_acr_log(path):
    with open(path, 'r') as f:
        log = json.load(f)
    
    output_file = 'acr_'+ path.split('/')[-1].split('.')[0] + '_output.txt'
    separator = '=' * 50
    separator = '\n' + separator + '\n'
    text = path
    for item in log:
        role = item['role']
        content = item['content']
        text +=  separator
        text += f'\n##{role}\n'
        text += content
        
    with open(output_file, 'w') as f:
        f.write(text)



def get_resolved_bugs(root_dir):
    resolved_bugs= []
    non_resolved_bugs = []

    for dire in os.listdir(root_dir):
        if dire.endswith(".json"):
            continue
        for file in os.listdir(os.path.join(root_dir, dire)):
            if file == 'evaluation_report.json':
                with open(os.path.join(root_dir, dire, file), "r") as f:
                    data = json.load(f)
                    if data["status"] == "RESOLVED_FULL":
                        resolved_bugs.append(dire)

    for bug in os.listdir(root_dir):
        if bug.endswith(".json"):
            continue
        if bug not in resolved_bugs:
            non_resolved_bugs.append(bug)
    
    # with open("resolved_bugs.json", "w") as f:
    #     json.dump(resolved_bugs, f, indent=4)
    
    # with open("non_resolved_bugs.json", "w") as f:
    #     json.dump(non_resolved_bugs, f, indent=4)

    return resolved_bugs


# print(len(get_resolved_bugs('/data/swe-fl/SRC/DebuggingAgent/exp/wo_debugging_acr_agentless_intersection_50_05061510')))

get_acr_log('/data/swe-fl/TRAJS/spec-rover-artifact/full/specrover/applicable_patch/astropy__astropy-12891_2024-07-30_08-47-55/agent_selection.json')


# with open('../data/acr_agentless_intersection_50.json','r') as f:
#     intersection_50 = json.load(f)

# bugs_increase_list = []
# resolved_bugs = set()
# root_dir = '/data/swe-fl/SRC/DebuggingAgent/exp'
# for dire in os.listdir(root_dir):
#     if dire.startswith('wo_debugging_acr_agentless_intersection_50_0504'):
#         path = os.path.join(root_dir, dire)
#         curr_resolved_bugs = get_resolved_bugs(path)
#         print(dire)
#         print(len(curr_resolved_bugs))
#         resolved_bugs.update(set(curr_resolved_bugs))
#         print(len(resolved_bugs))
#         bugs_increase_list.append(len(resolved_bugs))

# for bug in intersection_50:
#     if bug not in resolved_bugs:
#         print(bug)
        
        
        

