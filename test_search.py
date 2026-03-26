import os
import json
import requests
from bs4 import BeautifulSoup

def test_course_search():
    # 1. 检查凭证是否存在
    if not os.path.exists("auth_state.json"):
        print("❌ 找不到 auth_state.json，无法进行测试。")
        return

    # 2. 创建 Session 并注入 Cookie
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
    })
    
    with open("auth_state.json", 'r', encoding='utf-8') as f:
        state = json.load(f)
        for c in state.get('cookies', []):
            session.cookies.set(c['name'], c['value'], domain=c['domain'], path=c['path'])
            
    # 3. 构造请求 URL 和 搜索参数 (这就是 HTML 表单里的 input 和 select 标签)
    # 基础 URL 是 form 标签的 action 属性决定的
    url = "https://labor.seu.edu.cn/SJItemKaiKe/XuanKe" 
    
    # payload 中的键必须和 HTML 表单中的 name 属性一模一样
    params = {
        "SchoolTermCode": "",    # 学期，留空代表默认
        "PKPiCi": "",            # 排课批次
        "TeacherUserAccount": "",
        "TeacherUserName": "",
        "ItemName": "",
        "DeclareCategory": "生产劳动", # 👈 筛选条件 1：只看生产劳动
        "ZhuanYe": "",
        "IsXuanKe": "0",         
        "IsFull": "2",           # 👈 筛选条件 2：2 代表“否”（未满）
        "IsEnd": "2"             # 👈 筛选条件 3：2 代表“否”（未截止）
    }

    print("🚀 正在发送带参数的查询请求...")
    # 注意：GET 请求参数使用 params，POST 请求使用 data
    response = session.get(url, params=params, timeout=10)
    
    # 4. 验证是否被拦截 (极其关键的判断)
    if "auth.seu.edu.cn" in response.url:
        print("❌ 失败！系统不认你的 Cookie，把你踢到了登录页面：", response.url)
        return
        
    if response.status_code != 200:
        print(f"❌ 失败！服务器返回状态码: {response.status_code}")
        return

    # 5. 解析返回的表格结果
    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find(id='c_app_page_index_XuanKe_table')
    
    if not table:
        print("⚠️ 未找到表格结构，可能页面排版有变。")
        return
        
    tbody = table.find('tbody')
    rows = tbody.find_all('tr', class_='c--tr')
    
    if not rows:
        print("✅ 成功访问！但是当前条件下【暂无课程数据】。")
        return
        
    print(f"✅ 成功访问！按照你的筛选条件，找到了 {len(rows)} 门课：")
    for row in rows:
        tds = row.find_all('td')
        if len(tds) > 3:
            # 简单粗暴地提取第3和第4个单元格（可能是名称和类别，忽略偏移量简单测试）
            name = tds[2].get_text(strip=True)
            category = tds[3].get_text(strip=True)
            print(f" - {name} | {category}")

if __name__ == "__main__":
    test_course_search()