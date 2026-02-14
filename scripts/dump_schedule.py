from estimates_monitor import schedule
resp = schedule._fetch_schedule()
print(resp.url)
html = resp.text
with open('schedule.html','w',encoding='utf-8') as f:
    f.write(html)
print('saved')
