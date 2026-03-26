import time
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from datetime import datetime
# 从 account_manager.py 文件中，导入 UserAccount 这个类
from account_manager import UserAccount
import sqlite3
import os
import requests
from bs4 import BeautifulSoup
import re 
from dotenv import load_dotenv

load_dotenv()

# ============================================
# 数据库连接与操作
# ============================================

# 1. 连接到数据库（如果 labor.db 文件不存在，会自动在当前目录创建一个）
conn = sqlite3.connect('labor.db')
cursor = conn.cursor()

# 2. 初始化数据库结构（建表）
def init_db():
    # 创建用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            location TEXT,
            category TEXT,
            token TEXT UNIQUE NOT NULL
        )
    ''')
    
    # 创建推送历史表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS push_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            course_unique_id TEXT NOT NULL,
            UNIQUE(email, course_unique_id) -- 联合唯一索引，防止同一门课给同一个人存两遍
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS latest_courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kaike_id TEXT,
            name TEXT,
            category TEXT,
            location TEXT,
            week TEXT,
            time_info TEXT,
            status TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_info (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    conn.commit()
    print("数据库初始化完成！")


# 将最新抓取的课程全量覆盖写入数据库
def update_latest_courses(courses_list):
    # 先清空旧数据
    cursor.execute("DELETE FROM latest_courses")
    # 写入新数据
    for c in courses_list:
        cursor.execute('''
            INSERT INTO latest_courses (kaike_id, name, category, location, week, time_info, status) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            c['sj_item_kaike_id'], # 👈 新增：开课ID
            c['name'], 
            c['category'], 
            c['location'], 
            c.get('week', '未知'),   # 👈 新增：周次（用get防止旧数据报错）
            c['time'], 
            c['status']
        ))

    # 记录当前时间到 system_info 表
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        REPLACE INTO system_info (key, value) VALUES ('last_update', ?)
    ''', (now_str,))

    conn.commit()
    print("-> 已将最新课程快照同步至数据库，供网页读取。")


# 3. 添加新订阅用户的函数
def add_user(email, location, category):
    try:
        cursor.execute('''
            INSERT INTO users (email, location, category) 
            VALUES (?, ?, ?)
        ''', (email, location, category))
        conn.commit()
        print(f"成功添加用户: {email}")
    except sqlite3.IntegrityError:
        print(f"用户 {email} 已经存在了，可以直接执行更新操作。")

# 4. 检查与记录推送历史的函数
def should_push(email, course_unique_id):
    """检查是否已经推送过，如果没推送过则记录并返回 True"""
    cursor.execute('''
        SELECT 1 FROM push_history WHERE email = ? AND course_unique_id = ?
    ''', (email, course_unique_id))
    
    if cursor.fetchone():
        return False # 查到了记录，说明发过了，不推送
    else:
        # 没发过，插入记录并允许推送
        cursor.execute('''
            INSERT INTO push_history (email, course_unique_id) VALUES (?, ?)
        ''', (email, course_unique_id))
        conn.commit()
        return True



# ==========================================
# 模块 1：数据层与全局配置
# ==========================================

# SMTP 邮件发送方配置
SMTP_CONFIG = {
    "server": os.getenv("SMTP_SERVER", "smtp.qq.com"), 
    "port": int(os.getenv("SMTP_PORT", 465)),
    "user": os.getenv("SMTP_USER"),
    "auth_code": os.getenv("SMTP_AUTH_CODE")
}

# 2. 读取工具人账号 (如果没找到，默认返回 None)
TOOL_ACCOUNT = {
    "student_id": os.getenv("TOOL_STUDENT_ID"),
    "password": os.getenv("TOOL_PASSWORD")
}

# ==========================================
# 获取所有用户的工具函数
# ==========================================
def get_all_users():
    """从 SQLite 数据库中提取所有订阅用户"""
    cursor.execute("SELECT email, location, category, token FROM users")
    return cursor.fetchall()  # 返回格式: [('email1', '九龙湖', '生产'), ('email2',...)]


# 抓取间隔（秒）
CHECK_INTERVAL = 3 * 60


# ==========================================
# 模块 2：通知层 (Notifier)
# ==========================================

def send_email(to_email, subject, html_content):
    """
    发送 HTML 邮件给指定的单个用户
    """
    msg = MIMEMultipart()
    msg['From'] = formataddr(("SEU 选课中心 - Garvofadge", SMTP_CONFIG['user']))
    msg['To'] = to_email
    msg['Subject'] = subject

    # 将传入的 HTML 字符串附加到邮件中
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))

    try:
        server = smtplib.SMTP_SSL(SMTP_CONFIG['server'], SMTP_CONFIG['port'])
        server.login(SMTP_CONFIG['user'], SMTP_CONFIG['auth_code'])
        server.sendmail(SMTP_CONFIG['user'], [to_email], msg.as_string())
        server.quit()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 成功向 {to_email} 发送推送！")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 向 {to_email} 发送失败: {e}")



# ==========================================
# 模块 3：提取层 (Scraper) - 基于 Requests 和 BeautifulSoup
# ==========================================

# 清理文本的辅助函数
def clean_text(text):
    return " ".join(text.split()) if text else '无'


def fetch_latest_courses(session):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在请求选课数据...")
    url = "https://labor.seu.edu.cn/SJItemKaiKe/XuanKe/Index"
    
    try:
        # 1. 发送 HTTP 请求获取网页源码
        response = session.get(url, timeout=15)
        response.raise_for_status() # 检查是否返回 200 OK
    except Exception as e:
        print(f"网络请求失败，可能是Cookie失效或网络波动: {e}")
        return []

    # 2. 使用 BeautifulSoup 解析 HTML
    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find(id='c_app_page_index_XuanKe_table')
    
    if not table:
        print("未找到课程表格，可能是Cookie已过期或系统非开放时间。")
        return []

    courses = []
    # 找到 tbody 中的所有行 (排除可能隐藏的行或表头)
    tbody = table.find('tbody')
    if not tbody:
        return []
        
    rows = tbody.find_all('tr', class_='c--tr')

    for row in rows:
        # ==========================================
        # 步骤 1：精确提取后台隐藏 API 弹药 (绝对不会错位)
        # ==========================================
        course_info = {}
        for td_data in row.find_all('td-data'):
            key = td_data.get('data-name')
            val = td_data.get('data-value')
            if key:
                course_info[key] = val
                
        # 如果这行没藏着 SJItemKaiKeID，说明不是有效课程行，跳过
        if not course_info.get('SJItemKaiKeID'):
            continue

        # ==========================================
        # 步骤 2：用正则提取视觉展示数据 (无视前端排版变更)
        # ==========================================
        # 把这一行所有的纯文本连起来，方便正则搜索
        row_text = row.get_text(separator=" ", strip=True)

        # 提取时间：匹配类似 "2026-03-26 (2-5节)"
        time_match = re.search(r'\d{4}-\d{2}-\d{2}\s*\([\d-]+节\)', row_text)
        time_info = time_match.group(0).replace(" ", "") if time_match else course_info.get('PKPiCi', '未知')

        # 👇 【完美 DOM 提取法】：精准提取周次与星期
        schedule_set = set() # 使用集合(Set)自动去重
        
        # 1. 寻找这一行里所有负责显示时间的 dayOfWeek 卡片
        day_divs = row.find_all('div', class_='dayOfWeek')
        for d_div in day_divs:
            # 提取这个卡片里的所有干净文本块，正常会得到 ['第4周', '周三']
            text_parts = list(d_div.stripped_strings)
            if len(text_parts) >= 2:
                week_num = text_parts[0] # 第4周
                day_name = text_parts[1] # 周三
                # 组装并添加到集合中
                schedule_set.add(f"{week_num} {day_name}")

        # 2. 将集合排序并拼接，如果有多天有课，会变成 "第3周 周五 | 第4周 周三"
        if schedule_set:
            # 对集合排序可以保证周次小的排在前面，美观整洁
            week_info = " | ".join(sorted(schedule_set))
        else:
            week_info = "未知周次"

        # 提取选课人数：匹配类似 "8 / 30"
        capacity_match = re.search(r'\d+\s*/\s*\d+', row_text)
        capacity_info = capacity_match.group(0) if capacity_match else "未知"

        # 判断类别 (因为类别没在隐藏标签里，直接看文本包含什么)
        category = '生产劳动' if '生产劳动' in row_text else \
                   '生活劳动' if '生活劳动' in row_text else \
                   '服务劳动' if '服务劳动' in row_text else '特色品牌劳动'
        

        # ==========================================
        # 步骤 3：组装极其干净的数据字典
        # ==========================================
        courses.append({
            # 💡 直接用官方的开课实例 ID 做唯一防重主键！
            'unique_id': course_info['SJItemKaiKeID'], 
            'sj_item_id': course_info['SJItemID'],
            'sj_item_kaike_id': course_info['SJItemKaiKeID'],
            
            'name': course_info.get('ItemName', '未知'),
            'category': category,
            'location': course_info.get('CourseLocation', '未知'),
            'week': week_info,
            'time': time_info,
            'status': capacity_info,
            
            # 💡 网页上有现成的绿色的 "未满" 或 "已满" 徽章，直接利用！
            'is_full': '未满' not in row_text,  
            'is_expired': '已截止' in row_text
        })
        
    return courses



# ==========================================
# 模块 4：匹配层 (Matcher) - 已接入 SQLite
# ==========================================
def match_and_notify(all_courses):
    """
    将爬取到的课程与 SQLite 数据库中的规则进行比对
    """
    # 1. 全局粗筛：剔除已满或过期的课
    available_courses = [c for c in all_courses if not c['is_full'] and not c['is_expired']]

    print(f"-> 过滤已满和截止后：还剩 {len(available_courses)} 门可用课程。")
    
    if not available_courses:
        print("当前没有可用名额的课程。")
        return

    # 2. 从数据库获取真实订阅用户
    users = get_all_users()
    if not users:
        print("数据库中暂无订阅用户。")
        return

    # 3. 遍历每一个订阅用户
    for email, target_location, target_category, user_token in users:
        courses_to_push_for_this_user = []

        # 4. 遍历可用课程，检查是否符合要求
        for course in available_courses:
            match_location = target_location in course['location'] if target_location else True
            match_category = target_category in course['category'] if target_category else True
            
            if match_location and match_category:
                # 如果没发过，它会自动写入 push_history 表并返回 True
                if should_push(email, course['unique_id']):
                    courses_to_push_for_this_user.append(course)

        # 5. 发现新课，组装邮件并发送
        if courses_to_push_for_this_user:
            # 提前构造好退订链接和选课系统的登录链接
            base_url = os.getenv("BASE_URL", "http://127.0.0.1:5000")
            unsubscribe_link = f"{base_url}/unsubscribe/{user_token}"
            login_url = "https://labor.seu.edu.cn/SJItemKaiKe/XuanKe/Index"
            
            # 1. 邮件头部和主容器（带浅灰色背景和边框）
            html_body = f"""
            <div style="max-width: 600px; margin: 0 auto; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; background-color: #f9fbfd;">
                <div style="background-color: #198754; color: white; padding: 20px; text-align: center;">
                    <h2 style="margin: 0;">🎯 发现新课程！</h2>
                </div>
                <div style="padding: 30px;">
                    <p style="font-size: 16px; color: #333; margin-top: 0;">你好！系统为你监控到了符合要求的新课程：</p>
                    
                    <div style="background-color: #e9ecef; padding: 12px; border-radius: 4px; margin-bottom: 20px;">
                        <span style="font-size: 14px; color: #555;">🔍 <b>当前规则：</b> {target_location or '不限校区'} | {target_category or '不限类别'}</span>
                    </div>
                    
                    <div>
            """
            
            # 2. 遍历课程，为每一门课生成一个精美的“白底左侧蓝边”小卡片
            for c in courses_to_push_for_this_user:
                html_body += f"""
                    <div style="background-color: white; border-left: 4px solid #0d6efd; padding: 15px; margin-bottom: 15px; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                        <h4 style="margin: 0 0 10px 0; color: #0d6efd; font-size: 16px;">{c['name']}</h4>
                        <p style="margin: 5px 0; font-size: 14px; color: #555;">🏷️ <b>类别：</b> {c['category']}</p>
                        <p style="margin: 5px 0; font-size: 14px; color: #555;">📍 <b>地点：</b> {c['location']}</p>
                        <p style="margin: 5px 0; font-size: 14px; color: #555;">📅 <b>周次：</b> {c['week']} <span style="margin-left:15px; color:#198754;">📊 <b>人数：</b> {c['status']}</span></p>
                        <p style="margin: 5px 0; font-size: 14px; color: #555;">⏰ <b>时间：</b> {c['time']}</p>
                    </div>
                """
                
            # 3. 邮件底部：行动召唤按钮 (CTA) 和 退订链接
            html_body += f"""
                    </div>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{login_url}" style="display: inline-block; padding: 12px 25px; background-color: #0d6efd; color: white; text-decoration: none; border-radius: 5px; font-size: 16px; font-weight: bold;">立即前往系统选课</a>
                    </div>
                    
                    <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                    
                    <div style="text-align: center;">
                        <p style="font-size: 12px; color: #999; margin-bottom: 5px;">如果你已选满课程或不再需要接收此类提醒，请点击下方链接：</p>
                        <a href="{unsubscribe_link}" style="color: #dc3545; font-size: 12px; text-decoration: underline;">一键取消订阅</a>
                    </div>
                </div>
            </div>
            """

            # 发送邮件（稍微优化了标题，加上了课程数量）
            send_email(email, f"【SEU选课提醒】发现 {len(courses_to_push_for_this_user)} 门新课程", html_body)


# ==========================================
# 模块 5：调度层 (Scheduler)
# ==========================================

# 👇 配置你的抢课账号与目标 (请确保同目录下有对应的 JSON 文件)
USER_TARGETS = {
    "crimson": {
        "auth_file": "auth_state.json", 
        "categories": ["服务劳动"], # 该账号想抢的类别
        "quota": 1 # 抢满 1 门就停手
    },
    # 你可以继续解除下面这行的注释，添加更多同学
    # "李四(同学)": { "auth_file": "auth_lisi.json", "categories": ["生产劳动", "服务劳动", "生活劳动"], "quota": 2 }
}

# 记录每个账号的成功战绩
USER_SUCCESS_COUNT = {name: 0 for name in USER_TARGETS.keys()}


def main_loop():
    print("🛠️ 正在初始化抢课矩阵...")

    if not os.path.exists("auth_state.json"):
        print("❌ 致命错误：找不到 auth_state.json 文件！")
        print("请先在本地运行登录脚本生成凭证，并放到该目录下。")
        return
    
    #初始化狙击手：负责自动开火抢课
    snipers = []
    for name, config in USER_TARGETS.items():
        sniper = UserAccount(name, config["auth_file"])
        if sniper.is_valid:
            snipers.append(sniper)
    print(f"✅ 兵营就绪！当前存活自动抢课狙击手：{len(snipers)} 名\n")

    # 👇 修复 1：补上缺失的 Session 创建步骤，并伪装请求头
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    })

    # 2. 读取 Playwright 导出的 Cookie JSON，并塞入 Requests 的 Session 中
    try:
        with open("auth_state.json", 'r', encoding='utf-8') as f:
            state = json.load(f)
            
        cookies_loaded = 0
        for c in state.get('cookies', []):
            session.cookies.set(c['name'], c['value'], domain=c['domain'], path=c['path'])
            cookies_loaded += 1
        print(f"✅ 成功加载凭证！共读取到 {cookies_loaded} 个 Cookie。")
    except Exception as e:
        print(f"❌ 读取 auth_state.json 失败: {e}")
        return
    
    # 开启无限循环，定时抓取
    while True:
        current_courses = fetch_latest_courses(session)

        print(f"-> 网页解析完毕：共抓取到 {len(current_courses)} 门课程数据。")

        if current_courses:
            update_latest_courses(current_courses)
            match_and_notify(current_courses)

            #自动抢课逻辑
            available_courses = [c for c in current_courses if not c['is_full'] and not c['is_expired']]
            for course in available_courses:
                for sniper in snipers:
                    target_info = USER_TARGETS[sniper.identifier]
                    
                    # 检查配额，如果抢满了就跳过
                    if USER_SUCCESS_COUNT[sniper.identifier] >= target_info['quota']:
                        continue
                        
                    # 检查是不是自己想要的类别
                    if course['category'] in target_info['categories']:
                        success = sniper.shoot(course)
                        if success:
                            USER_SUCCESS_COUNT[sniper.identifier] += 1
                            print(f"  🏆 [{sniper.identifier}] 当前战绩: {USER_SUCCESS_COUNT[sniper.identifier]}/{target_info['quota']}")
                        
                        time.sleep(1) # 狙击手开枪间隔，防封IP
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 本轮处理完毕，休眠 {CHECK_INTERVAL/60} 分钟...")
        # 👇 修复 3：将 asyncio.sleep 换成普通的 time.sleep
        time.sleep(CHECK_INTERVAL)

# ==========================================
# 统一的程序入口 (Main)
# ==========================================
if __name__ == "__main__":
    # 初始化数据库表结构
    init_db()
    
    # 启动异步爬虫主循环
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\n程序被手动中断，正在安全关闭数据库...")
        conn.close()