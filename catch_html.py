import os
import json
import requests
import time
from bs4 import BeautifulSoup
from datetime import datetime

def set_a_trap():
    if not os.path.exists("auth_state.json"):
        print("❌ 找不到 auth_state.json，无法布下捕兽夹。")
        return

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
    })
    
    with open("auth_state.json", 'r', encoding='utf-8') as f:
        state = json.load(f)
        for c in state.get('cookies', []):
            session.cookies.set(c['name'], c['value'], domain=c['domain'], path=c['path'])
            
    url = "https://labor.seu.edu.cn/SJItemKaiKe/XuanKe" 
    
    # 💡 捕兽夹参数：故意把类别留空，只要有任何“未满”的课出现，我们都抓！
    params = {
        "SchoolTermCode": "",
        "PKPiCi": "",
        "DeclareCategory": "", 
        "IsFull": "2",  # 未满
        "IsEnd": "2"    # 未截止
    }

    print("🕵️ 捕兽夹已布下！正在潜伏监控，只要有任何活的课程出现，立刻捕获并保存源码...")

    while True:
        now = datetime.now().strftime('%H:%M:%S')
        try:
            response = session.get(url, params=params, timeout=10)
            
            if "auth.seu.edu.cn" in response.url:
                print(f"\n[{now}] ❌ Cookie已失效，被踢回登录页。捕兽夹已损坏，请重新登录！")
                break
                
            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find(id='c_app_page_index_XuanKe_table')
            
            if table:
                tbody = table.find('tbody')
                rows = tbody.find_all('tr')
                
                # 检查第一行的文字
                first_row_text = rows[0].get_text(strip=True) if rows else ""
                
                if "暂无数据" not in first_row_text and len(rows) > 0:
                    print(f"\n[{now}] 🎉 警报！警报！发现活的课程了！共 {len(rows)} 条！")
                    
                    # 立刻保存案发现场
                    filename = f"course_captured_{datetime.now().strftime('%H%M%S')}.html"
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(response.text)
                        
                    print(f"💾 网页源码已成功保存为：{filename}")
                    print("👉 请用代码编辑器打开这个 HTML 文件，搜索 'SJItemID'，查看完整的隐藏结构！")
                    break  # 抓到一次就大功告成，退出循环
                else:
                    print(f"[{now}] 宁静的校园，暂无课程数据...")
                    
        except Exception as e:
            print(f"[{now}] 网络波动，捕兽夹摇晃了一下: {e}")

        # 每 60 秒看一眼，避免请求过频被封
        time.sleep(60)

if __name__ == "__main__":
    set_a_trap()