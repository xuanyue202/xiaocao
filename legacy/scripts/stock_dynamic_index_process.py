import requests
import pandas as pd
import time
import random
import json

# 小草当日环境 'indexType': 0

def normalize_dynamic_index(arr, parent = '', date = ''):
    norm_results = []
    for elem in arr:
        norm_results.append({'categoryCode': '', 'blockCode': '', 'parent': parent, 'date': date,
                             **{k: v for k, v in elem.items() if k != 'blockDynamicIndexList'}})
        if isinstance(elem.get('blockDynamicIndexList'), list):
            norm_results.extend(normalize_dynamic_index(elem['blockDynamicIndexList'],
                                                        elem['categoryCode'], elem['date']))
    return norm_results


with open('results/xiaocao_dynamic_index_0.json', 'r') as f:
    dynamic_index = json.load(f)

pd.DataFrame(normalize_dynamic_index(dynamic_index)).to_csv(
    'results/xiaocao_dynamic_index_all_0.csv', index=False)