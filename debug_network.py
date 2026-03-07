import asyncio
from browser.session import BrowserManager

async def debug_network():
    bm = BrowserManager()
    page = await bm.init_browser()
    
    print("[Debug] Loading feed first...")
    await page.goto('https://www.linkedin.com/feed/', wait_until='domcontentloaded')
    await asyncio.sleep(5)
    print(f"[Debug] Feed URL: {page.url}")
    
    # Listen to console and network
    page.on("console", lambda msg: print(f"CONSOLE [{msg.type}]: {msg.text}"))
    page.on("requestfailed", lambda req: print(f"REQUEST FAILED: {req.url} - {req.failure}"))
    page.on("response", lambda res: print(f"RESPONSE [{res.status}]: {res.url}") if res.status >= 400 else None)
    
    print("[Debug] Resetting SPA state...")
    await page.goto("about:blank")
    
    print("[Debug] Navigating to search...")
    search_url = 'https://www.linkedin.com/jobs/search/?keywords=Backend+Developer&location=Brazil&f_WT=2&f_AL=true&start=0'
    await page.goto(search_url, wait_until='domcontentloaded')
    
    print("[Debug] Waiting 20 seconds for rendering...")
    await asyncio.sleep(20)
    
    cards = await page.locator('div[data-job-id], li[data-occludable-job-id]').count()
    divs = await page.locator('div').count()
    
    print(f"[Debug] Final stats - Cards: {cards}, Divs: {divs}")
    
    await bm.close()

if __name__ == "__main__":
    asyncio.run(debug_network())
