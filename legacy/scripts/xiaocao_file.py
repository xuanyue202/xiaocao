import requests
import pandas as pd
import time
import random
import json


def get_code_list(date, groups=3, sort=False):
    """
    get all code list by group 代码列表
    :param date: e.g. '2024-10-25'
    :param groups: 0 连板接力 jsjl 12; 1 竞王 1097；2 红盘 jssb 348； 3 低吸 cjs  73 ；
    """
    group_arr = ['jsjl', 'xcjw', 'jssb', 'cjs']
    field = group_arr[groups]

    df = pd.read_csv('results/' + date + '_detail.csv')
    filtered = df[df[field] != 0]
    if sort:
        filtered = filtered.sort_values(ascending=False, by=field)
    return filtered['code'].to_list()

# if __name__ == '__main__':
#     json = get_code_list('2024-10-25')
#     print(json)
#     print(len(json))

def get_block_category_rank(date, model=0):
    """
    get block category rank 板块大类
    :param date: e.g. '2024-10-25'
    :param model: 0 or 1；
    """
    with open('results/archive/xiaocao_industry_block_category_rank_all_local_0.json', 'r') as f:
        block_category_ranks = json.load(f)
    return [v for v in block_category_ranks if v['tradeDate'] == date]

# if __name__ == '__main__':
#     json = get_block_category_rank('2024-10-25')
#     print(json)
#     print(len(json))

def get_index(date, stock_list):
    """
    get xiao cao index 个股信息
    :param date: e.g. '2024-10-25'
    :param stock_list: list of codes
    """
    df = pd.read_csv('results/' + date + '_detail.csv')
    df.set_index('code', inplace=True)

    query = pd.DataFrame.from_dict({'code': stock_list}).set_index('code')
    json_result = df.join(query, on='code', how='right').transpose().to_dict()
    return [{'code': k, **v} for k, v in json_result.items()]


def get_index_with_check(date, stock_list, check_field=None):
    """
    get xiao cao index 个股信息，如果没加载完就返回None
    :param date: e.g. '2024-10-25'
    :param stock_list: list of codes
    :param check_field: e.g. 'xcjw' 检查该字段是否空
    """
    indices = get_index(date, stock_list)
    for index in indices:
        if index['isWeak'] is None:
            # not loaded, therefore not ready for all
            return None
        if check_field is not None and index[check_field] is None:
            return None
    return indices


#
# if __name__ == '__main__':
#     json = get_index_with_check('2024-10-25', [
#             "000560.XSHE",
#             "600101.XSHG",
#             "301248.XSHE",
#             "601890.XSHG",
#             "600676.XSHG",
#             "002305.XSHE",
#             "600992.XSHG",
#             "300198.XSHE",
#             "600732.XSHG",
#             "300519.XSHE",
#             "300423.XSHE",
#             "603618.XSHG",
#             "300068.XSHE",
#             "000526.XSHE",
#             "000430.XSHE",
#             "002897.XSHE",
#             "603095.XSHG",
#             "002903.XSHE",
#             "002548.XSHE",
#             "001311.XSHE",
#             "301118.XSHE",
#             "603004.XSHG",
#             "688639.XSHG",
#             "300868.XSHE",
#             "002103.XSHE",
#             "002864.XSHE",
#             "601208.XSHG",
#             "002023.XSHE",
#             "600789.XSHG",
#             "600281.XSHG",
#             "300085.XSHE",
#             "300885.XSHE",
#             "301080.XSHE",
#             "002565.XSHE",
#             "300666.XSHE",
#             "000639.XSHE",
#             "600975.XSHG",])
#     print(json)
#     print(len(json))


def get_industry_block_rank(date, model=0):
    """
    get industry block rank 当日方向 短线重点
    :param date: e.g. '2024-10-25'
    :param model: 0 or 1；
    """
    df = pd.read_csv('results/archive/xiaocao_industry_block_all_0.csv')
    json_result = df[df['date'] == date].transpose().to_dict()
    return [v for _, v in json_result.items()]


# if __name__ == '__main__':
#     json = get_industry_block_rank('2024-10-25')
#     print(json)
#     print(len(json))


def wait_for_a_while():
    random_sleep_time = random.uniform(0.1, 0.3)
    time.sleep(random_sleep_time)


def get_sorted_code_list(date):
    """
    获取竞王排序列表
    :param date:
    """
    return get_code_list(date, 1, True)