import os
import asyncio
from playwright.async_api import async_playwright, Page, BrowserContext
from playwright_stealth import stealth_async
from core.config import USER_DATA_DIR, HEADLESS_MODE, PROXY_SERVER, PROXY_USERNAME, PROXY_PASSWORD

class BrowserManager:
    def __init__(self):
        self._playwright = None
        self._browser_context = None
        self._page = None

    async def init_browser(self) -> Page:
        """Initializes a persistent browser context with Playwright."""
        self._playwright = await async_playwright().start()
        
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--start-maximized",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--test-type"
        ]

        proxy_config = None
        if PROXY_SERVER:
            proxy_config = {
                "server": PROXY_SERVER,
            }
            if PROXY_USERNAME and PROXY_PASSWORD:
                proxy_config["username"] = PROXY_USERNAME
                proxy_config["password"] = PROXY_PASSWORD

        # Prepare userdata dir
        os.makedirs(USER_DATA_DIR, exist_ok=True)

        self._browser_context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=HEADLESS_MODE,
            args=launch_args,
            ignore_default_args=["--enable-automation", "--disable-extensions"],
            proxy=proxy_config,
            no_viewport=True,
            record_video_dir=None # Optional: we can add this for debugging later
        )

        # Get primary page
        pages = self._browser_context.pages
        self._page = pages[0] if pages else await self._browser_context.new_page()

        # Apply stealth via extension
        await stealth_async(self._page)
        
        return self._page

    async def get_page(self) -> Page:
        """Returns the current page or initializes it if not ready."""
        if not self._page:
            return await self.init_browser()
        return self._page

    async def close(self):
        """Cleanly closes the browser context."""
        if self._browser_context:
            await self._browser_context.close()
        if self._playwright:
            await self._playwright.stop()
