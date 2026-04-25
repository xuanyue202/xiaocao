import xiaocao_api as client
import stock_recommend
import datetime
import time

today = datetime.date.today()

if today.isoweekday() >= 6:
    print('周末愉快，不工作哦')

current_date = str(today)
print('Hello, 今天是', current_date)

now = time.gmtime()
while now.tm_hour * 60 + now.tm_min < 85:
    print('中国时间9点25之前，稍安勿躁')
    time.sleep(10)
    now = time.gmtime()

code_list = []
detail_ready = None
while detail_ready is None:
    code_list = client.get_sorted_code_list(current_date)
    client.wait_for_a_while()
    detail_ready = client.get_index_with_check(current_date, code_list[:10], 'xcjw')

print('10秒后开始工作啦')
time.sleep(10)

stock_recommend.get_recommendation_by_date(current_date, client)

