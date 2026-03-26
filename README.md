# 🎓 SEU 劳动教育课程监控与推送系统

基于 Python + Playwright + Flask 构建的自动化服务。用于实时监控东南大学劳动教育系统的最新课程名额，并通过HTML 邮件向订阅用户发送上课提醒。

## ✨ 核心特点 (Features)

* 🚀 **架构**：分离的异步后台爬虫引擎 (`labor_monitor.py`) 与轻量级 Web 前端看板 (`app.py`)，互不阻塞。
* 🛡️ **鉴权**：采用 **Storage State (凭证移植)** 技术，在本地手动验证一次后，服务器免密登录，绕过校园网 CAS 系统的设备风控策略。
* 📧 **邮件分发**：支持多用户独立订阅。系统会根据用户设定的“校区”与“劳动类别”进行交叉匹配，发现新课后立即推送邮件。
* 🪶 **数据管理**：采用 **SQLite3** 单文件数据库，数据迁移只需拷贝一个 `labor.db` 文件。

---

## 🛠️ 环境准备 (Prerequisites)

在开始部署之前，请确保服务器满足以下条件：
* 操作系统：Ubuntu 20.04+ 或 Debian 11+（推荐）
* Python 版本：**Python 3.8** 或以上
* 开放服务器防火墙端口：`5000` (用于访问 Web 看板)

---

## 🚀 详细部署步骤 (Deployment)

### 第一步：获取代码与安装依赖

1. 将项目代码克隆或上传到服务器的指定目录（例如 `/opt/seu_labor_monitor`）。
2. 在项目根目录下，安装所需的 Python 库：
```bash
# 推荐先创建一个虚拟环境 (可选)
python3 -m venv venv
source venv/bin/activate

# 安装核心依赖库
pip install playwright flask python-dotenv

# 安装 Playwright 的无头浏览器内核及系统依赖（此步耗时较长，请耐心等待）
playwright install chromium --with-deps
```

### 第二步：配置环境变量

1. 复制环境模板文件：
```bash
cp .env.example .env
```
2. 使用 `nano` 或 `vim` 编辑 `.env` 文件，填入你的真实信息：
```env
# 邮件发件箱配置 (必须填写，注意 Auth Code 是授权码而非登录密码)
SMTP_SERVER=smtp.qq.com
SMTP_PORT=465
SMTP_USER=your_email@foxmail.com
SMTP_AUTH_CODE=your_auth_code_here

# Flask 网站安全密钥 (随便敲一串长长的乱码即可)
FLASK_SECRET_KEY=e8f9a7b6c5d4e3f2g1h0

# 网站公网地址 (部署后改为你的服务器 IP 或绑定的域名)
BASE_URL=http://你的服务器公网IP:5000
```

### 第三步：生成并上传“免密登录凭证”（关键！）

由于学校的 CAS 系统拦截无头浏览器，**你必须先在自己的个人电脑（有界面的系统）上获取身份凭证**。

1. 在你的**本地电脑**上，运行 `get_login_state.py`。
2. 弹出的浏览器会自动打开学校统一身份认证系统，请手动输入账号、密码并完成**手机短信验证码**的验证。
3. 登录成功后，脚本会自动在本地目录下生成一个 `auth_state.json` 文件。
4. 将这个 `auth_state.json` 文件上传到**服务器的项目根目录**下。

### 第四步：使用 PM2 守护进程并在后台运行服务

为了让网站和爬虫在你关闭 SSH 终端后依然 24 小时运行，我们推荐使用 `pm2` 来管理进程。

1. 如果服务器没安装 Node.js 和 PM2，请先安装：
```bash
sudo apt update
sudo apt install npm
sudo npm install -g pm2
```

2. 启动 Web 看板服务 (`app.py`)：
```bash
pm2 start app.py --name "seu-web" --interpreter python3
```

3. 启动后台爬虫引擎 (`labor_monitor.py`)：
```bash
pm2 start labor_monitor.py --name "seu-scraper" --interpreter python3
```

4. 保存 PM2 进程列表（开机自启）：
```bash
pm2 save
pm2 startup
```

---

## 💻 访问与使用

部署完成后，打开浏览器访问：
👉 `http://你的服务器公网IP:5000`

你可以在这里：
1. 提交自己的测试邮箱，体验全自动的订阅流程。
2. 查看当前系统内实时剩余的劳动教育课程名额。
3. 在左下角查看脱敏后的订阅用户列表。

---

## ⚙️ 常用维护命令 (FAQ)

**查看程序运行日志（排错时非常有用）：**
```bash
pm2 logs seu-scraper  # 查看爬虫抓取情况
pm2 logs seu-web      # 查看网站访问和发信情况
```

**如果遇到凭证过期（一般一个月左右）：**
如果日志中提示 `凭证可能已失效或被拦截`，只需在本地电脑重新运行一次 `get_login_state.py`，把新的 `auth_state.json` 覆盖到服务器上，然后重启爬虫即可：
```bash
pm2 restart seu-scraper
```

---
### ⚠️ 免责声明
本项目仅供 Python 自动化技术学习与交流使用。使用本脚本所产生的一切后果由使用者自行承担。请合理设置轮询频率（默认3分钟），避免对校园网服务器造成不必要的压力。