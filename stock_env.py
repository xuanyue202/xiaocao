import requests
import pandas as pd
import time
import random

headers = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7,en-GB;q=0.6',
    'content-type': 'application/json',
    'origin': 'https://www.topxlc.com',
    'priority': 'u=1, i',
    'referer': 'https://www.topxlc.com/',
    'sec-ch-ua': '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'user-agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) ' +
                  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36',
}

dates = ['2024-10-25', '2024-10-24', '2024-10-23', '2024-10-22', '2024-10-21', '2024-10-18', '2024-10-17',
         '2024-10-16', '2024-10-15', '2024-10-14', '2024-10-11', '2024-10-10', '2024-10-09', '2024-10-08',
         '2024-09-30', '2024-09-27', '2024-09-26', '2024-09-25', '2024-09-24', '2024-09-23', '2024-09-20',
         '2024-09-19', '2024-09-18', '2024-09-13', '2024-09-12', '2024-09-11', '2024-09-10', '2024-09-09',
         '2024-09-06', '2024-09-05']

stocks = pd.read_json('stocks.json')

max_retries = 3
min_sleep_time = 0.1
max_sleep_time = 0.7

content = []
for current_date in dates:
    print(current_date)
    json_data = {
        'params': {
            'code': '9A0001,9A0002,9A0003,9B0001,9B0002,9B0003,9C0001',
            'date': current_date,
        },
    }

    random_sleep_time = random.uniform(0.3, 5)
    time.sleep(random_sleep_time)
    retries = 0
    while retries < max_retries:
        random_sleep_time = random.uniform(min_sleep_time, max_sleep_time)
        time.sleep(random_sleep_time)
        try:
            response = requests.post('https://p-xcapi.topxlc.com/stock/xiao_cao_environment_second_line',
                                     headers=headers, json=json_data)
            response.raise_for_status()  # 检查响应状态码
            content.extend([{'date': current_date, **v} for v in response.json()['result']])
            break  # 如果请求成功，跳出重试循环
        except requests.exceptions.HTTPError as errh:
            print(f"HTTP Error: {errh}")
        except requests.exceptions.ConnectionError as errc:
            print(f"Error Connecting: {errc}")
        except requests.exceptions.Timeout as errt:
            print(f"Timeout Error: {errt}")
        except requests.exceptions.RequestException as err:
            print(f"OOps: Something Else: {err}")
        retries += 1
        if retries < max_retries:
            print(f"尝试重新发送请求... ({retries}/{max_retries})")

pd.DataFrame(content).to_csv('results/xiaocao_env_detail.csv', index=False)
