import os
import re
import json
import time
import tiktoken
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.memory import ConversationBufferMemory
from typing import Optional
from httpx import RemoteProtocolError, HTTPError

from swe_log import log_msg, log_and_print, init_logger
from retrieve_src import retrieve_code_element

# Set OpenAI API key and base URL
api_base = "https://api5.xhub.chat/v1/"  
# api_base = "https://api.kksj.org/v1"
# api_base = 'https://cluster1-qwen.cxpcn.site/v1'
api_key = "sk-VrP154liNPBQ80JvAfA579Bc16E34bD7Ae6774A19cC6352e"  
# api_key = 'sk-HC4m7yZO9mQaYIs9nCONuLQQgnc8MKGGS99GGtw7RHXaTZC8'

os.environ["OPENAI_API_KEY"] = api_key
os.environ["OPENAI_API_BASE"] = api_base  


class LLMModel:
    def __init__(self, model_name: str, system_message: str, instance):
        self.instance = instance
        self.model = ChatOpenAI(model=model_name, temperature=0.8)
        self.system_message = system_message
        self.memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    

    def query_model(self, user_message: str, retain_memory: bool = False) -> str:

        if retain_memory and self.memory.chat_memory.messages:
            messages = self.memory.chat_memory.messages.copy()
        else:
            messages = [SystemMessage(content=self.system_message)]
        
        messages.append(HumanMessage(content=user_message))

        # log_and_print(user_message)

        success_flag = False
        retries = 5
        while not success_flag and retries > 0:
            try:
                start_time = time.time()
                query_result = self.model.invoke(messages)
                
                response = query_result.content
                success_flag = True
            
            except (RemoteProtocolError, HTTPError) as e:
                retries -= 1
                log_msg(f"Connection or HTTP error occurred: {e}. Retries left: {retries}")
                time.sleep(2)  
            except Exception as e:
                retries -= 1
                log_msg(f"An unexpected error occurred: {e}. Retries left: {retries}")
            finally:
                log_and_print(f"Query time: {time.time() - start_time:.2f} seconds")
        
        if retries == 0 and not success_flag:
            log_msg("Exceeded maximum retry attemptsw while querying LLM. Raising exception.")
            raise ValueError("Exceeded maximum retry attempts.")

                
        if retain_memory:
            messages.append(HumanMessage(content=response))  
            self.memory.save_context({"input": user_message}, {"output": response})
        
        # log_and_print('='*200)
        # log_and_print(response)

        return response

    def clear_memory(self):
        self.memory.clear()
    

    def modify_memory_content(self, 
                            target_pattern: str, 
                            replacement: str = "[REDACTED]") -> int:
        # Set regex flags based on case sensitivity
        pattern = re.compile(target_pattern, flags=re.DOTALL)
        
        modified_count = 0
        # Iterate through all chat messages while preserving metadata
        for msg in self.memory.chat_memory.messages:
            original_content = msg.content
            # Preserve message type (human/AI), only modify content
            new_content = pattern.sub(replacement, original_content)
            
            # Update if content changed
            if new_content != original_content:
                msg.content = new_content
                modified_count += 1
                # Log modification details (truncated to 50 chars)
                log_msg(f"Modify memory: Original:{original_content[:50]}...New memory:{new_content[:50]}...")

        return modified_count


if __name__ == "__main__":
    system_msg = "你是一个有帮助的助手。"
    init_logger('/data/SWE/SRC/approach/tmp/log/temp')
    llm_query = LLMModel(model_name="gpt-3.5-turbo-0125", system_message=system_msg)
    
    response1 = llm_query.query_model("你好，介绍一下自己。记住我的小狗是白色的。", retain_memory=False, json_flag = False)
    print("Response1:", response1)
    
    response2 = llm_query.query_model("能告诉我上次的对话吗？从现在开始你的名字叫<runtime-info>RUNTIME</runtime-info>", retain_memory=True)
    print("Response2:", response2)
    
    response3 = llm_query.query_model("现在的对话是什么？你的名字叫什么", retain_memory=True)
    print("Response3:", response3)

    print(llm_query.memory)

    result = llm_query.modify_memory_content(r'<runtime-info>.*?</runtime-info>')
    print(result)

    print(llm_query.memory)

    response3 = llm_query.query_model("现在的对话是什么？你的名字叫什么", retain_memory=True)
    print("Response3:", response3)
