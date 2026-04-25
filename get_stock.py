json_data = {
    'params': {
        'groups': '1',
        'date': '2024-10-25',
    },
}

# 1 竞王 1097；2 红盘 348； 3 低吸  73 ；0 接力 12

response = requests.post('https://p-xcapi.topxlc.com/stock/focus_xiao_cao_index/get_code_list',
                         headers=headers, json=json_data)

json_data = {
    'params': {
        'queryType': 1,
        'sortId': 38,
        'sortType': 1,
        'type': 0,
        'date': '2024-10-25',
    },
}

# {
#   "params": {
#     "queryType": 1,
#     "sortId": 38,
#     "sortType": 0,
#     "type": 0,
#     "date": "2024-10-25"
#   }
# }

response = requests.post('https://p-xcapi.topxlc.com/stock/sort', headers=headers, json=json_data)
