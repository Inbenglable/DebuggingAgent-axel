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
        self.model = ChatOpenAI(model=model_name)
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
            
        detailed_chat_dir = Path(f"/data/swe-fl/SRC/DebuggingAgent/log/{self.instance['instance_id']}/chat")
        if not detailed_chat_dir.exists():
            detailed_chat_dir.mkdir(parents=True)
        
        cur_index = 0
        for file in os.listdir(detailed_chat_dir):
            file_index = int(file.split("_")[0])
            if file_index > cur_index:
                cur_index = file_index
        with open(detailed_chat_dir / f"{cur_index + 1}_input.txt", "w") as f:
            for msg in messages:
                f.write(msg.content + "\n")
        with open(detailed_chat_dir / f"{cur_index + 1}_output.txt", "w") as f:
            f.write(response + "\n")
                
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


# def remove_ansi_escape_sequences(text: str) -> str:
#     """
#     Removes ANSI escape sequences from the text.
#     """
#     ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
#     return ansi_escape.sub('', text)

# def num_tokens_from_messages(messages: Any, model: str = "gpt-3.5-turbo-0301") -> int:
#     """
#     Returns the number of tokens used by a list of messages.
    
#     Args:
#         messages (list or str): The messages to count tokens for.
#         model (str): The model name to determine token encoding. Defaults to "gpt-3.5-turbo-0301".
    
#     Returns:
#         int: The number of tokens.
#     """
#     try:
#         encoding = tiktoken.encoding_for_model(model)
#     except KeyError:
#         encoding = tiktoken.get_encoding("cl100k_base")
    
#     if isinstance(messages, list):
#         # Calculate the total number of tokens for all messages
#         num_tokens = 0
#         for message in messages:
#             content = message.content if hasattr(message, 'content') else message
#             num_tokens += len(encoding.encode(content))
#     else:
#         num_tokens = len(encoding.encode(messages))
    
#     return num_tokens

# def initialize_langchain_model(
#     model: str = "gpt-3.5-turbo",
#     temperature: float = 1.0,
#     max_retries: int = 40,
#     request_timeout: int = 100
# ) -> ChatOpenAI:
#     """
#     Initializes the LangChain ChatOpenAI model.
    
#     Args:
#         model (str): The model name. Defaults to "gpt-3.5-turbo".
#         temperature (float): Sampling temperature. Defaults to 1.0.
#         max_retries (int): Maximum number of retry attempts. Defaults to 40.
#         request_timeout (int): Timeout for API requests in seconds. Defaults to 100.
    
#     Returns:
#         ChatOpenAI: An instance of LangChain's ChatOpenAI model.
#     """
#     llm = ChatOpenAI(
#         model_name=model,
#         temperature=temperature,
#         request_timeout=request_timeout,
#         openai_api_key=os.getenv("OPENAI_API_KEY"),
#         openai_api_base=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
#         max_retries=max_retries
#     )
#     return llm

# def handle_api_request(config: Dict[str, Any], base_url: str = api_base, max_retries: int = 40, timeout: int = 100) -> str:
#     """
#     Handles the API request with retry logic.
    
#     Args:
#         config (dict): Configuration for the API request.
#         base_url (str): The base URL for the API. Defaults to api_base.
#         max_retries (int): Maximum number of retry attempts. Defaults to 40.
#         timeout (int): Timeout for each request in seconds. Defaults to 100.
    
#     Returns:
#         str: The content of the API response.
#     """
#     raw_result = None
#     retries = 0

#     # Initialize the OpenAI client with the custom base URL
#     openai.api_base = base_url

#     while raw_result is None and retries < max_retries:
#         try:
#             # Attempt to get the completion
#             raw_result = openai.ChatCompletion.create(**config)
#         except openai.error.OpenAIError as e:
#             if isinstance(e, openai.error.BadRequestError):
#                 logger.exception("Invalid API Request")
#                 raise Exception("Invalid API Request") from e
#             elif isinstance(e, openai.error.RateLimitError):
#                 logger.exception("Rate limit exceeded. Retrying in 5 seconds...")
#                 time.sleep(5)
#             elif isinstance(e, openai.error.APIConnectionError):
#                 logger.exception("API connection error. Retrying in 5 seconds...")
#                 time.sleep(5)
#             else:
#                 logger.exception("An unexpected error occurred. Retrying in 1 second...")
#                 time.sleep(1)
#         retries += 1

#     if raw_result is not None:
#         return raw_result.choices[0].message.content
#     else:
#         raise Exception("Failed to get a response from the API after multiple retries.")

# def request_openai_api(
#     user_message: str,
#     llm: ChatOpenAI,
#     system_message: str = "You are a helpful assistant.",
#     batch_size: int = 1
# ) -> str:
#     """
#     Sends a request to the OpenAI API and returns the response.
    
#     Args:
#         user_message (str): The user's message to send.
#         llm (ChatOpenAI): The LangChain ChatOpenAI model instance.
#         system_message (str): The system message. Defaults to "You are a helpful assistant.".
#         batch_size (int): Number of responses to generate. Defaults to 1.
    
#     Returns:
#         str: The assistant's response.
#     """
#     # Clean the user message by removing ANSI escape sequences
#     clean_message = remove_ansi_escape_sequences(user_message)
#     # logger.info(f"Query LLM: {clean_message}")

#     # Create a list of messages including the system prompt and user message
#     messages = [
#         SystemMessage(content=system_message),
#         HumanMessage(content=clean_message)
#     ]

#     # Calculate the number of tokens in the request
#     tokens = num_tokens_from_messages(messages, model=llm.model_name)
#     # logger.info(f"Number of tokens in the request: {tokens}")

#     # Prepare the configuration for the API request
#     config = {
#         "model": llm.model_name,
#         "temperature": llm.temperature,
#         "messages": [
#             {"role": "system", "content": system_message},
#             {"role": "user", "content": clean_message},
#         ],
#         "n": batch_size,
#     }

#     # Send the API request with custom handling
#     try:
#         responses = handle_api_request(config)
#         # Log each response if batch_size > 1
#         # if batch_size > 1:
#             # logger.info(f"Received {batch_size} responses from LLM.")
#         # logger.info(f"LLM Response: {responses}")
#         return responses
#     except Exception as e:
#         # logger.exception("An error occurred while requesting the OpenAI API.")
#         raise e

# # Example usage
# if __name__ == "__main__":
#     # Initialize the LangChain model
#     llm = initialize_langchain_model(
#         model="gpt-3.5-turbo",
#         temperature=0.7
#     )

#     # User input
#     user_input = "Hello, can you tell me what the weather is like today?"

#     # Send the request and get the response
#     try:
#         response = request_openai_api(
#             user_message=user_input,
#             llm=llm,
#             system_message="You are a helpful assistant.",
#             batch_size=1
#         )
#         print("LLM Response:", response)
#     except Exception as e:
#         # logger.error(f"Failed to get response: {e}")
#         print(f"Failed to get response: {e}")
