import requests
import time
def query_model(prompt, n):
    gpt_response_lst = []
    response = api_response('user', prompt, n)
    for choice in response['choices']:
        if choice['message']:
            content = choice['message']['content']
            gpt_response_lst.append(content)
    return gpt_response_lst


def api_response(gpt_role, prompt, sample_size):
    api_key = 'sk-VrP154liNPBQ80JvAfA579Bc16E34bD7Ae6774A19cC6352e'

    headers = {'Authorization': api_key, 'Content-Type': 'application/json', }
    json_data = {
        'model': 'gpt-4o-2024-05-13',
        'messages': [{
            'role': gpt_role,
            'content': prompt }, ],
        'stream': False,
        'temperature': 0.8,
        'n': sample_size,
        
    }

    while True:
        try:
            response = requests.post(
                # api_base = "https://api.kksj.org/v1"
                'https://api5.xhub.chat/v1/chat/completions',
                headers=headers,
                json=json_data,
                timeout=120  # 加一个超时更稳
            )
            response.raise_for_status()  # 如果不是 2xx，会抛出 HTTPError

            response_json = response.json()

            if not response_json or 'choices' not in response_json:
                raise ValueError("No valid 'choices' in response")

            return response_json  # 成功返回

        except requests.HTTPError as e:
            print(f"HTTP error: {e}")
            if e.response is not None:
                print(f"Status Code: {e.response.status_code}")
                try:
                    print(f"Error Response: {e.response.json()}")
                except Exception:
                    print(f"Error Response (non-JSON): {e.response.text}")
            time.sleep(10)

        except requests.RequestException as e:
            print(f"Request exception (可能网络问题): {e}")
            time.sleep(10)

        except ValueError as e:
            print(f"Value error: {e}")
            time.sleep(10)

    return response_json
# 调API部分结束


if __name__ == "__main__":
    with open('tmp.txt','r') as f:
        text =  f.read()
    print(query_model(text,1))
    # print(query_model(input(),1))