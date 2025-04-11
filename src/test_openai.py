from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.memory import ConversationBufferMemory
import os


api_base = "https://api5.xhub.chat/v1/"
api_key = "sk-VrP154liNPBQ80JvAfA579Bc16E34bD7Ae6774A19cC6352e" 
os.environ["OPENAI_API_KEY"] = api_key
os.environ["OPENAI_API_BASE"] = api_base
model_name = 'gpt-4o-2024-08-06'

system_message = 'you are a debugging agent'

with open('tmp.txt','r') as f:
    user_message =  f.read()

model = ChatOpenAI(model=model_name)
messages = [SystemMessage(content=system_message)]
messages.append(HumanMessage(content=user_message))
query_result = model.invoke(messages)

response = query_result.content

print(response)