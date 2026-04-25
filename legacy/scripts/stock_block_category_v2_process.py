import requests
import pandas as pd
import time
import random
import json

# 板块大类 'indexType': 0, result.localCategoryRankList[0]
def normalize(arr, parent = ''):
    norm_results = []
    for elem in arr:
        norm_results.append({'categoryCode': '', 'blockCode': '', 'parent': parent, 'dataType': '', 'industryType': '',
                             **{k: v for k, v in elem.items() if k != 'blockRankList'}})
        if isinstance(elem.get('blockRankList'), list):
            norm_results.extend(normalize(elem['blockRankList'], elem['categoryCode']))
    return norm_results


with open('results/xiaocao_industry_block_category_rank_all_local_0.json', 'r') as f:
    block_category_rank = json.load(f)

pd.DataFrame(normalize(block_category_rank)).to_csv(
    'results/xiaocao_industry_block_category_rank_local_0.csv', index=False)

