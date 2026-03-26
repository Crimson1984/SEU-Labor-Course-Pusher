import asyncio
from playwright.async_api import async_playwright

async def save_auth_state():
    async with async_playwright() as p:
        # 必须是有头模式，让你能看到画面去点验证码
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print("浏览器已打开，请手动完成登录和手机验证码验证...")
        await page.goto("https://auth.seu.edu.cn/dist/#/dist/main/login?service=https://labor.seu.edu.cn/UnifiedAuth/CASLogin")

        # 让程序挂起，等待你手动操作。
        try:
            await page.wait_for_url("**/System/Home**", timeout=120000) # 给你2分钟时间收验证码
            print("登录成功！正在保存设备凭证...")
            
            # 【核心魔法】：把当前浏览器的所有 Cookie 和缓存保存到一个 JSON 文件里
            await context.storage_state(path="auth_state.json")
            print("凭证已保存至 auth_state.json！")
            
        except Exception as e:
            print("登录超时或出错，请重试。")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(save_auth_state())