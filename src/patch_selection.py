from prompt import PATCH_SELECTION_HEAD, PATCH_SELECTION_INSTRUCT, PATCH_SELECTION_AGENT_SYSTEM_MSG
from model import LLMModel

MODEL_NAME = 'gpt-4o'

def build_patch_selection_prompt(patch_list, instance):
    patches_prompt = ''
    
    
    patch_select_prompt = PATCH_SELECTION_HEAD.format(
        project = instance['repo'].split('/')[1],
        issue = instance['problem_statement']
    )
                                                      
    
    agent = LLMModel(model_name=MODEL_NAME, system_message=PATCH_SELECTION_AGENT_SYSTEM_MSG, instance = instance)
    