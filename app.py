from flask import Flask, render_template, request, redirect, flash
import sqlite3
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
# 如果找不到环境变量中的 key，就默认生成一个随机的，防止报错
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24))


# 👇邮箱发件配置
SMTP_CONFIG = {
    "server": os.getenv("SMTP_SERVER", "smtp.qq.com"), 
    "port": int(os.getenv("SMTP_PORT", 465)),
    "user": os.getenv("SMTP_USER"),
    "auth_code": os.getenv("SMTP_AUTH_CODE")
}

def get_db_connection():
    # Flask 每次处理网页请求时，独立连接数据库，防止多线程冲突
    conn = sqlite3.connect('labor.db')
    conn.row_factory = sqlite3.Row # 让查询结果表现得像字典
    return conn

def send_welcome_email(to_email, location, category, token):
    """发送订阅成功通知信"""
    # 构造退订链接 (注意：部署到服务器时要把 127.0.0.1 换成你的服务器 IP 或域名)
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:5000")
    # 动态构造退订链接
    unsubscribe_link = f"{base_url}/unsubscribe/{token}"
    
    # 设计一封美观的 HTML 欢迎信
    html_content = f"""
    <div style="max-width: 600px; margin: 0 auto; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
        <div style="background-color: #0d6efd; color: white; padding: 20px; text-align: center;">
            <h2 style="margin: 0;">🎉 订阅成功！</h2>
        </div>
        <div style="padding: 30px; background-color: #f8f9fa;">
            <p style="font-size: 16px; color: #333;">你好！</p>
            <p style="font-size: 16px; color: #333;">你已成功订阅 <b>东南大学劳动教育课程监控</b>。</p>
            
            <div style="background-color: white; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #0d6efd;">
                <p style="margin: 5px 0; color: #555;">📍 <b>目标校区：</b> {location or '不限校区'}</p>
                <p style="margin: 5px 0; color: #555;">🏷️ <b>劳动类别：</b> {category or '不限类别'}</p>
            </div>
            
            <p style="font-size: 14px; color: #666;">爬虫引擎会每 3 分钟巡视一次选课系统。一旦发现符合你要求且未满员的新课，我们将立刻通过此邮箱通知你。</p>
            <br>
            <hr style="border: 0; border-top: 1px solid #eee;">
            <div style="text-align: center; margin-top: 20px;">
                <p style="font-size: 12px; color: #999;">如果这不是你的操作，或你以后不想再收到提醒，可以随时点击下方按钮退订：</p>
                <a href="{unsubscribe_link}" style="display: inline-block; padding: 10px 20px; background-color: #dc3545; color: white; text-decoration: none; border-radius: 4px; font-size: 14px; font-weight: bold;">一键取消订阅</a>
            </div>
        </div>
    </div>
    """

    msg = MIMEMultipart()
    msg['From'] = formataddr(("SEU 选课脚本 - Garvofadge", SMTP_CONFIG['user']))
    msg['To'] = to_email
    msg['Subject'] = "【订阅成功】SEU 劳动教育课程监控助手"
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))

    # 使用异步或多线程发邮件最好，但为了简单，这里直接同步发送
    try:
        server = smtplib.SMTP_SSL(SMTP_CONFIG['server'], SMTP_CONFIG['port'])
        server.login(SMTP_CONFIG['user'], SMTP_CONFIG['auth_code'])
        server.sendmail(SMTP_CONFIG['user'], [to_email], msg.as_string())
        server.quit()
        print(f"欢迎邮件已成功发送至 {to_email}")
    except Exception as e:
        print(f"欢迎邮件发送失败: {e}")

# 路由 1：首页大厅（展示课程）
@app.route('/')
def index():
    conn = get_db_connection()
    # 读取最新的课程列表
    courses = conn.execute('SELECT * FROM latest_courses').fetchall()
    # 读取当前的订阅人数
    user_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    # 👇 新增：读取所有的订阅用户数据
    users_list = conn.execute('SELECT * FROM users ORDER BY id DESC').fetchall()
    safe_users_list = []
    for user in users_list:
        user_dict = dict(user) # 假设取出的是 sqlite.Row，转为字典
        user_dict['masked_email'] = mask_email(user_dict['email'])
        safe_users_list.append(user_dict)

    # 👇 新增：读取最后更新时间
    row = conn.execute("SELECT value FROM system_info WHERE key='last_update'").fetchone()
    # 如果刚建库还没抓取过，就显示"爬虫正在初始化"
    last_update_time = row['value'] if row else "爬虫正在初始化..."

    conn.close()
    
    return render_template('index.html', courses=courses, user_count=user_count, last_update_time=last_update_time, users_list=safe_users_list)

# 路由 2：处理表单提交（添加订阅）
@app.route('/subscribe', methods=['POST'])
def subscribe():
    email = request.form['email']
    location = request.form['location']
    category = request.form['category']
    
    # 简单的非空校验
    if not email:
        flash("邮箱不能为空！", "danger")
        return redirect('/')
    
    user_token = uuid.uuid4().hex
        
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO users (email, location, category, token) 
            VALUES (?, ?, ?, ?)
        ''', (email, location, category, user_token))
        conn.commit()

        # 👇 新增：数据库写入成功后，立刻发送欢迎邮件！
        send_welcome_email(email, location, category, user_token)
        
        flash(f"成功订阅！一封确认邮件已发送至 {email}，请查收。", "success")

    except sqlite3.IntegrityError:
        flash("该邮箱已经订阅过了哦，请勿重复提交。", "warning")
    finally:
        conn.close()
        
    return redirect('/')


# 👇 路由 3：处理邮件中的一键退订链接（注意这里变成了 <token>，并且默认是 GET 请求）
@app.route('/unsubscribe/<token>')
def unsubscribe(token):
    conn = get_db_connection()
    try:
        # 通过 token 寻找这个用户
        user = conn.execute('SELECT email FROM users WHERE token = ?', (token,)).fetchone()
        
        if user:
            email = user['email']
            # 从用户表和推送历史表中彻底删除
            conn.execute('DELETE FROM users WHERE token = ?', (token,))
            conn.execute('DELETE FROM push_history WHERE email = ?', (email,))
            conn.commit()
            flash(f"已成功取消 {email} 的劳动教育课程订阅。感谢支持!", "success")
        else:
            flash("退订失败：该退订链接无效或已过期。", "danger")
    except Exception as e:
        flash(f"系统错误: {e}", "danger")
    finally:
        conn.close()
        
    return redirect('/')

def mask_email(email):
    """
    邮箱掩码函数：
    123456789@qq.com -> 123****89@qq.com
    admin@gmail.com -> ad***@gmail.com
    a@foxmail.com -> a***@foxmail.com
    """
    if not email or '@' not in email:
        return email
    
    name, domain = email.split('@', 1)
    if len(name) <= 2:
        masked_name = name + '***'
    elif len(name) <= 5:
        masked_name = name[:2] + '***'
    else:
        # 保留前3位和后2位，中间打星号
        masked_name = name[:3] + '****' + name[-2:]
        
    return f"{masked_name}@{domain}"

if __name__ == '__main__':
    # 启动网站，监听 5000 端口，开启调试模式
    app.run(host='0.0.0.0', port=5000, debug=True)