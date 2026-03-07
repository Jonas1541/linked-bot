import asyncio
import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core.config import USER_DATA_DIR, HEADLESS_MODE, PROXY_SERVER, PROXY_USERNAME, PROXY_PASSWORD

job_id = "4375955379"

async def extract_html():
    print("Starting playwright...")
    async with async_playwright() as p:
        # Format proxy
        playwright_proxy = None
        if PROXY_SERVER:
            playwright_proxy = {"server": PROXY_SERVER}
            if PROXY_USERNAME and PROXY_PASSWORD:
                playwright_proxy["username"] = PROXY_USERNAME
                playwright_proxy["password"] = PROXY_PASSWORD
                
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-software-rasterizer",
        ]
        
        # Launch persistent context
        print("Launching context...")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=True,
            proxy=playwright_proxy,
            args=launch_args
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        # Go to feed to ensure we're logged in
        print("Going to feed...")
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        await asyncio.sleep(5)
        
        print("Extracting cookies...")
        page_cookies = await context.cookies()
        httpx_cookies = {c["name"]: c["value"] for c in page_cookies}
        
        await context.close()
        
    print("Fetching job via httpx...")
    mobile_user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
    headers = {"User-Agent": mobile_user_agent, "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"}
    job_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
    
    httpx_proxy = None
    if PROXY_SERVER:
        if PROXY_USERNAME and PROXY_PASSWORD:
            scheme, host_port = PROXY_SERVER.split("://")
            httpx_proxy = f"{scheme}://{PROXY_USERNAME}:{PROXY_PASSWORD}@{host_port}"
        else:
            httpx_proxy = PROXY_SERVER
            
    async with httpx.AsyncClient(proxies=httpx_proxy, timeout=30.0) if httpx_proxy else httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(job_url, headers=headers, cookies=httpx_cookies)
        html = resp.text
        
        with open("test_job_ssr.html", "w", encoding="utf-8") as f:
            f.write(html)
            
        print("Saved to test_job_ssr.html")
        
        # Check for apply button indicators
        print(f"jobs-apply-button in html: {'jobs-apply-button' in html}")
        print(f"Candidatura simplificada in html: {'Candidatura simplificada' in html}")
        print(f"Easy Apply in html: {'Easy Apply' in html}")
        print(f"Apply in html: {'Apply' in html}")
        
        soup = BeautifulSoup(html, "html.parser")
        buttons = soup.find_all("button")
        for b in buttons:
            print("BUTTON:", b.get_text(strip=True), b.get("class"), b.get("data-view-name"))
        
if __name__ == "__main__":
    asyncio.run(extract_html())
