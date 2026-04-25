import ast

import pandas as pd

import xiaocao_file
import xiaocao_api

SUPER_JW = 300
STRONG_JW = 200
QUALIFIED_JW = 150
SOSO_JW = 100


def pick_big_ones(arr, upper_num=5):
    top = arr[0]['num']
    rank = 0
    arr[0]['r'] = 0
    cur_top = top
    picked = [arr[0]]
    for i in range(1, upper_num):
        if arr[i]['num'] < cur_top - 20 or arr[i]['num'] < top * 0.8:
            return picked
        else:
            if arr[i]['num'] < cur_top - 5:
                rank += 1
                cur_top = arr[i]['num']
            arr[i]['r'] = rank
            picked.append(arr[i])
    return picked


def get_picked_block(detail, picked_block):
    return _get_picked(detail, 'blockCodeList', picked_block, 'blockCode')


def get_picked_block_category(detail, picked_block_category):
    return _get_picked(detail, 'blockCategoryCodeList', picked_block_category, 'categoryCode')


def _get_picked(detail, key, picked, picked_key):
    current = detail[key]
    if isinstance(current, str):
        current = ast.literal_eval(current)
    elif not isinstance(current, list):
        return []
    return [{'n': v[picked_key], 'r': v['r']} for v in picked if v[picked_key] in current]


def get_focus_rank(focus):
    if len(focus) == 0:
        return -1
    return focus[0]['r']


def get_direction_obj(block_focus, category_focus):
    is_focus = len(block_focus) > 0 or len(category_focus) > 0
    return {'focus': is_focus, '方向': len(block_focus), '方向排名': get_focus_rank(block_focus),
            '方向大类': len(category_focus), '大类排名': get_focus_rank(category_focus)}


def compare_jw(detail, jw_score, focus_obj):
    return detail['xcjw'] >= jw_score or (focus_obj['focus'] and detail['xcjw'] >= jw_score / 1.3)


def focus_suffix(focus_obj):
    if not focus_obj['focus']:
        return ''
    elif focus_obj['方向'] > 0:
        return '-方向' + str(focus_obj['方向排名'])
    elif focus_obj['方向大类'] > 0:
        return '-大类' + str(focus_obj['大类排名'])
    return ''


def detail_focus_header(title, detail, focus_obj):
    return {'模式': title, '方向': focus_suffix(focus_obj), 'code': detail['code'], '名称': detail['codeName'],
            '竞王': detail['xcjw'], '低吸': detail['cjs'], '连板接力': detail['jsjl'], '红盘': detail['jssb'],
            '当日': detail['entityPctChangeRate'], **focus_obj}


# 0 连板接力 jsjl 12; 1 竞王 xcjw 1097；2 红盘 jssb 348； 3 低吸 cjs  73 ；
def check_lianban(sorted_lianban_details, picked_block, picked_category):
    result = []
    for detail in sorted_lianban_details:
        if detail['xcjw'] < STRONG_JW / 1.3:
            break
        # 弱 昨日连板 = 1
        if detail['isWeak'] != 1 or detail['ylimitupdays'] != 1 or float(detail['jsjl']) <= 0:
            continue

        block_focus = get_picked_block(detail, picked_block)
        category_focus = get_picked_block_category(detail, picked_category)
        focus_obj = get_direction_obj(block_focus, category_focus)

        if compare_jw(detail, SUPER_JW, focus_obj):
            result.append({**detail_focus_header('接力低弱转1', detail, focus_obj), **detail})
        # 开幅 > 1%
        if detail['openPctChangeRate'] >= 1.0 and compare_jw(detail, STRONG_JW, focus_obj):
            result.append({**detail_focus_header('接力低弱转2', detail, focus_obj), **detail})
    return result


def check_dixi(sorted_dixi_details, picked_block, picked_category):
    result = []
    for detail in sorted_dixi_details:
        if detail['xcjw'] < QUALIFIED_JW / 1.3:
            break
        # # 弱 昨日连板 = 1
        # if detail['isWeak'] != 1 or detail['ylimitupdays'] != 1 or float(detail['jsjl']) <= 0:
        #     continue

        block_focus = get_picked_block(detail, picked_block)
        category_focus = get_picked_block_category(detail, picked_category)
        focus_obj = get_direction_obj(block_focus, category_focus)

        '''
        | 4 全盘低位低吸 | 短线非主跌       | 低位   |      |              |      | >200          |      | 前 2 名 |
        | 低位首红断     | 短线非主跌       | 首红断 |      |              |      | 最低标准> 150 |      | 第 1 名 |
        '''
        # | 5 绿断低吸     |                  | 绿断   |    | >150          |      | 有分    |
        if detail['isDownBroken'] == 1 and compare_jw(detail, QUALIFIED_JW, focus_obj) and detail['cjs'] > 0:
            result.append({**detail_focus_header('绿断低吸', detail, focus_obj), **detail})
        # | 6 红断低吸     | 短线非主跌＋连板 | 红断   |      | 看一作二空三 |      | 最低标准> 150 |      | 有分    |
        if detail['isUpBroken'] == 1 and compare_jw(detail, QUALIFIED_JW, focus_obj) and detail['cjs'] > 0:
            result.append({**detail_focus_header('红断低吸', detail, focus_obj), **detail})

        if focus_obj['focus']:
            '''
            | 方向低位低吸 | 短线非主跌 | 低位     |      |      |      | >200  |      | 前 3名 |
            '''
            # | N字低吸     | 短线非主跌 | N 半以下 |      |      |      | > 200 |      | 有分   |
            if detail['isHalf'] == 1 and compare_jw(detail, STRONG_JW * 1.3, focus_obj) and detail['cjs'] > 0:
                result.append({**detail_focus_header('N字低吸', detail, focus_obj), **detail})
            # | 孕线低吸 | 短线非主跌 | 孕线 | | | | > 150 | | > 100 |
            if (detail['isGestationLine'] == 1 and compare_jw(detail, QUALIFIED_JW * 1.3, focus_obj)
                    and detail['cjs'] > 100):
                result.append({**detail_focus_header('孕线低吸', detail, focus_obj), **detail})
    return result


def get_index_with_pagination(client, date, stock_list, page_num=30):
    content = []
    for i in range(0, len(stock_list), page_num):
        print('current stock:', i, '/', len(stock_list))
        current_page = stock_list[i: i + 20]
        client.wait_for_a_while()
        content.extend(client.get_index(date, current_page))
    return content


def get_recommendation_by_date(date, client):
    print('get code list ...')
    lianban_codes = pd.DataFrame.from_dict({'code': client.get_code_list(date, 0)}).set_index('code')
    qibao_codes = pd.DataFrame.from_dict({'code': client.get_code_list(date, 2)}).set_index('code')
    dixi_codes = pd.DataFrame.from_dict({'code': client.get_code_list(date, 3)}).set_index('code')
    sorted_codes = pd.DataFrame.from_dict({'code': client.get_sorted_code_list(date)}).set_index('code')
    client.wait_for_a_while()

    print('get directions ...')
    block_category_rank = client.get_block_category_rank(date)
    block_category_rank.sort(key=lambda x: x['num'], reverse=True)
    picked_category = pick_big_ones(block_category_rank, 3)

    block_rank = client.get_industry_block_rank(date)
    block_rank.sort(key=lambda x: x['num'], reverse=True)
    picked_block = pick_big_ones(block_rank)

    sorted_lianban = sorted_codes.join(lianban_codes, how='inner', on='code').index.tolist()
    sorted_qibao = sorted_codes.join(qibao_codes, how='inner', on='code').index.tolist()
    sorted_dixi = sorted_codes.join(dixi_codes, how='inner', on='code').index.tolist()

    print('get index ...')
    sorted_lianban_details = get_index_with_pagination(client, date, sorted_lianban)
    #sorted_qibao_details = get_index_with_pagination(client, date, sorted_qibao)
    sorted_dixi_details = get_index_with_pagination(client, date, sorted_dixi)

    output = []
    output.extend(check_lianban(sorted_lianban_details, picked_block, picked_category))
    output.extend(check_dixi(sorted_dixi_details, picked_block, picked_category))
    pd.DataFrame(output).to_csv('output/result_' + date + '.csv', index=False)


if __name__ == '__main__':
    get_recommendation_by_date('2024-10-25', xiaocao_file)
    get_recommendation_by_date('2024-10-28', xiaocao_api)
