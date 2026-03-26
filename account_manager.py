import os
import json
import requests
from bs4 import BeautifulSoup

class UserAccount:
    """
    用户身份类：每个实例代表一个独立的用户（狙击手）
    拥有完全隔离的 Session、Cookie 和 CSRF Token
    """
    def __init__(self, identifier, auth_file):
        self.identifier = identifier  # 用户标识（比如姓名或学号）
        self.auth_file = auth_file    # 对应的 json 凭证文件路径
        
        # 1. 核心：为该用户创建一个完全独立的隔离容器
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest", # 提前准备好 AJAX 伪装
            "Referer": "https://labor.seu.edu.cn/SJItemKaiKe/XuanKe/Index"
        })
        
        self.csrf_token = ""
        self.is_valid = False
        
        # 初始化：加载Cookie并获取专属 Token
        self._load_credentials()
        self.refresh_csrf_token()

    def _load_credentials(self):
        """读取对应的 JSON 文件并注入 Cookie"""
        if not os.path.exists(self.auth_file):
            print(f"❌ [{self.identifier}] 找不到凭证文件 {self.auth_file}")
            return
            
        try:
            with open(self.auth_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                for c in state.get('cookies', []):
                    self.session.cookies.set(c['name'], c['value'], domain=c['domain'], path=c['path'])
            print(f"✅ [{self.identifier}] Cookie 加载成功！")
        except Exception as e:
            print(f"❌ [{self.identifier}] Cookie 加载失败: {e}")

    def refresh_csrf_token(self):
        """访问选课主页，为当前用户提取专属的 CSRF Token"""
        url = "https://labor.seu.edu.cn/SJItemKaiKe/XuanKe/Index"
        try:
            # 注意：获取 Token 必须用普通的 GET 请求，此时不需要发 AJAX 伪装头
            response = self.session.get(url, timeout=10)
            
            # 检查是否 Cookie 过期被踢回登录页
            if "auth.seu.edu.cn" in response.url:
                print(f"⚠️ [{self.identifier}] 凭证已过期，请重新抓取 json！")
                self.is_valid = False
                return

            soup = BeautifulSoup(response.text, 'html.parser')
            token_input = soup.find('input', {'name': '__RequestVerificationToken'})
            
            if token_input:
                self.csrf_token = token_input['value']
                # 提取成功后，直接把 Token 绑死在这个用户的 Session 请求头里
                self.session.headers.update({"__RequestVerificationToken": self.csrf_token})
                self.is_valid = True
                print(f"🎯 [{self.identifier}] 专属防伪令牌 (CSRF Token) 获取成功！")
            else:
                print(f"⚠️ [{self.identifier}] 未在页面中找到 CSRF Token。")
                self.is_valid = False
                
        except Exception as e:
            print(f"❌ [{self.identifier}] 刷新 Token 失败: {e}")

    def shoot(self, course):
        """狙击动作：以该用户的身份发送抢课 POST 请求"""
        if not self.is_valid:
            print(f"🚫 [{self.identifier}] 身份状态无效，无法开枪。")
            return False
            
        print(f"🔫 [{self.identifier}] 正在抢课：{course['name']}...")
        api_url = "https://labor.seu.edu.cn/SJItemKaiKe/XuanKe/StudentXuanKe"
        
        payload = {
            "SJItemID": course['sj_item_id'],
            "SJItemKaiKeID": course['sj_item_kaike_id']
        }
        
        try:
            # 直接使用该用户自带 Token 的 session 发送请求
            response = self.session.post(api_url, data=payload, timeout=5)
            result = response.json()
            
            if result.get('Success') is True:
                print(f"🎉 [{self.identifier}] 捷报！[{course['name']}] 抢课成功！")
                return True
            else:
                msg = result.get('Message', '未知原因')
                print(f"⚠️ [{self.identifier}] 抢课失败: {msg}")
                # 如果提示 Token 错误，可能需要触发 self.refresh_csrf_token()
                if "防伪" in msg or "Token" in msg:
                    print(f"🔄 [{self.identifier}] 尝试重新获取 Token...")
                    self.refresh_csrf_token()
                return False
                
        except Exception as e:
            print(f"❌ [{self.identifier}] 开火时卡壳: {e}")
            return False