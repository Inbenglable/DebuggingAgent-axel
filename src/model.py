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
from retrieve_src import retrieve_code_and_comment

# Set OpenAI API key and base URL
api_base = "https://api5.xhub.chat/v1/"  
# api_base = "https://api.kksj.org/v1"
# api_base = 'https://cluster1-qwen.cxpcn.site/v1'
api_key = "sk-VrP154liNPBQ80JvAfA579Bc16E34bD7Ae6774A19cC6352e"  
# api_key = 'sk-HC4m7yZO9mQaYIs9nCONuLQQgnc8MKGGS99GGtw7RHXaTZC8'

os.environ["OPENAI_API_KEY"] = api_key
os.environ["OPENAI_API_BASE"] = api_base  

def extract_trace_reply(response: str):

    # 匹配 buggy/observed method，支持带反引号和加粗 Markdown **
    method_pattern = r"\*{0,2}([Bb]uggy [Mm]ethod|[Oo]bserved [Mm]ethod)\*{0,2}:\s*`?([^:`\n]+):([^:`\n]+)`?"

    # 匹配 observed scope，可以是单行或范围，也支持加粗 key
    scope_pattern = r"\*{0,2}[Oo]bserved [Ss]cope\*{0,2}:\s*`?([^:`\n]+):(\d+)(?:-(\d+))?`?"

    if match := re.search(method_pattern, response):
        return {
            "type": match.group(1),
            "file": match.group(2).strip(),
            "method": match.group(3).strip()
        }
    elif match := re.search(scope_pattern, response):
        start_line = int(match.group(2))
        end_line = int(match.group(3)) if match.group(3) else start_line
        return {
            "type": "Observed scope",
            "file": match.group(1).strip(),
            "start_line": start_line,
            "end_line": end_line
        }
    else:
        raise ValueError("Invalid trace reply format.")
    
    
def extract_json_instruction(wrapped_json_str: str) -> str:
    # ```json\nCONTENT\n```
    match_json = re.search(r'```json\s*\n(.*?)\n```', wrapped_json_str, re.DOTALL)
    # log_and_print(match_json)
    if match_json:
        try:
            json_obj = json.loads(match_json.group(1).strip())
            return json_obj
        except json.JSONDecodeError as e:
            log_msg(f"Error decoding JSON: {e}")
            raise e
    else:
        raise ValueError("No JSON content found in the response.")
    

class LLMModel:
    def __init__(self, model_name: str, system_message: str, instance):
        self.instance = instance
        self.model = ChatOpenAI(model=model_name)
        self.system_message = system_message
        self.memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    

    def query_model(self, user_message: str, retain_memory: bool = False, flag_type: str = None, instance = None) -> str:
        encoding = tiktoken.get_encoding("cl100k_base")

        if retain_memory and self.memory.chat_memory.messages:
            messages = self.memory.chat_memory.messages.copy()
        else:
            messages = [SystemMessage(content=self.system_message)]
        
        messages.append(HumanMessage(content=user_message))


        # Determine whether json obj is successfully generated, if not, regenerate
        success_flag = False
        response = ''
        retries = 5

        while not success_flag and retries > 0:
            
            try:
                start_time = time.time()
                # input_text = ''
                # for msg in messages:
                #     input_text+=msg.content
                # print(input_text)
                query_result = self.model.invoke(messages)

                response = query_result.content

                if not flag_type:
                    success_flag = True
                else:
                    if flag_type == 'json':
                        try:
                            extract_json_instruction(response)
                            success_flag = True
                        except (ValueError, json.JSONDecodeError) as e:
                            log_and_print(f"Retrying to generate a valid JSON response...\nErr: {e}")
                            retries -= 1
                    elif flag_type == 'choose_method':
                        try:
                            trace_reply = extract_trace_reply(response)
                            if trace_reply['type'].lower() == 'buggy method' or trace_reply['type'].lower() == 'observed method':
                                file_name = trace_reply['file']
                                if not os.path.exists(file_name):
                                    abs_file_path = instance['testbed_src_path'] / file_name
                                else:
                                    abs_file_path = file_name
                                if os.path.exists(abs_file_path):
                                    retrieve_result = retrieve_code_and_comment(abs_file_path, trace_reply['method'])
                                    if len(retrieve_result) > 0:
                                        success_flag = True
                            if not success_flag:
                                raise ValueError("Invalid trace reply format.")
                        except ValueError as e:
                            log_and_print(f"Retrying to generate a valid METHOD CHOOSING response...\nErr: {e}")
                            retries -= 1
                    elif flag_type == 'choose_scope':
                        try:
                            trace_reply = extract_trace_reply(response)
                            if trace_reply['type'].lower() == 'buggy method' or trace_reply['type'].lower() == 'observed scope':
                                file_name = trace_reply['file']
                                if not os.path.exists(file_name):
                                    abs_file_path = instance['testbed_src_path'] / file_name
                                else:
                                    abs_file_path = file_name
                                if os.path.exists(abs_file_path):
                                    observed_start_line = trace_reply['start_line']
                                    observed_end_line = trace_reply['end_line']
                                    retrieve_result = retrieve_code_and_comment(abs_file_path, f'{observed_start_line}-{observed_end_line}')
                                    if len(retrieve_result) > 0:
                                        success_flag = True
                            if not success_flag:
                                raise ValueError("Invalid trace reply format.")
                        except ValueError as e:
                            log_and_print(f"Retrying to generate a valid SCOPE CHOOSING response...\nErr: {e}")
                            retries -= 1
                        

            except (RemoteProtocolError, HTTPError) as e:
                log_and_print(f"Connection or HTTP error occurred: {e}. Retries left: {retries}")
                retries -= 1
                time.sleep(2)  
            except Exception as e:
                log_and_print(f"An unexpected error occurred: {e}. Retries left: {retries}")
                retries -= 1
            finally:
                # input_text = ''
                # for msg in messages:
                #     input_text+=msg.content
                # input_token_len = len(encoding.encode(input_text))
                # output_token_len = len(encoding.encode(response))
                end_time = time.time()
                # print(f'input token: {input_token_len}; output token: {output_token_len}')
                log_and_print(f"Query time: {end_time - start_time:.2f} seconds")

            if retries == 0:
                log_and_print("Exceeded maximum retry attempts. Raising exception.")
                raise ValueError("Exceeded maximum retry attempts.")

            if not success_flag:
                log_and_print(f'Retrying.... Times left: {retries}')
            
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
                # input_text += msg.content
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
        """
        Ministry of Truth-style memory editor (1984 reference)
        Performs in-place modification of conversation history by replacing specified patterns
        
        :param target_pattern: Content pattern to erase (supports regex)
        :param replacement: Replacement placeholder (default: [REDACTED])
        :param case_sensitive: Case-sensitive matching (default: False)
        :return: Number of modified messages
        """
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
