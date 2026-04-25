import requests
import pandas as pd
import time
import random
import xiaocao_api as xiaocao

# '2024-10-25', '2024-10-24', '2024-10-23',
dates = ['2024-10-22', '2024-10-21', '2024-10-18', '2024-10-17',
         '2024-10-16', '2024-10-15', '2024-10-14', '2024-10-11', '2024-10-10', '2024-10-09', '2024-10-08',
         '2024-09-30', '2024-09-27', '2024-09-26', '2024-09-25', '2024-09-24', '2024-09-23', '2024-09-20',
         '2024-09-19', '2024-09-18', '2024-09-13', '2024-09-12', '2024-09-11', '2024-09-10', '2024-09-09',
         '2024-09-06', '2024-09-05']

stocks = pd.read_json('stocks.json')

max_retries = 3
min_sleep_time = 0.1
max_sleep_time = 0.7

for current_date in dates:
    print(current_date)
    content = []
    for i in range(0, len(stocks), 20):
        print('current stock:', i, '/', len(stocks))
        stock_list = stocks[i: i + 20].apply(lambda x: ','.join(x)).sum()
        xiaocao.wait_for_a_while()
        content.extend(xiaocao.get_index(current_date, stock_list))

    pd.DataFrame(content).to_csv('results/' + current_date + '_detail.csv', index=False)
