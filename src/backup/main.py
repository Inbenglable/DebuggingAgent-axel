import json
import time
from datasets import load_dataset
from log import init_logger, print_banner
from model import request_openai_api
from prompt import REPRODUCE_ISSUE

# Take simple swe task, astropy_12907



def init_workspace():
    global SWE_DATASET
    SWE_DATASET = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")

    init_logger('/data/SWE/SRC/approach/src/demo.log')


def main():
    init_workspace()

    reproduce_result = {}

    for index in range(len(SWE_DATASET)):

        print_banner(SWE_DATASET['instance_id'][index])

        repair_overview = REPRODUCE_ISSUE.format(
            issue_description=SWE_DATASET['problem_statement'][index]
            )

        result = request_openai_api(repair_overview, max_tokens=1000, batch_size=5, model='gpt-4o')

        reproduce_result[SWE_DATASET['instance_id'][index]] = []

        for reproduce_test_sample in result.choices:
            reproduce_result[SWE_DATASET['instance_id'][index]].append(
                reproduce_test_sample.message.content
                    )

        time.sleep(1)

        with open('/data/SWE/SRC/approach/tmp/reproduce_gpt4o.json', 'w') as f:
            json.dump(reproduce_result, f)

    # target_instance_index = SWE_DATASET['instance_id'].index('astropy__astropy-12907')

    # repair_overview = REPRODUCE_ISSUE.format(\
    #     issue_description=SWE_DATASET['problem_statement'][target_instance_index])
    # print(repair_overview)
    
    # result = request_openai_api(repair_overview, 1000)
    
    pass


if __name__ == '__main__':
    main()