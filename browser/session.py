import os
import asyncio
from playwright.async_api import async_playwright, Page, BrowserContext, Route
from playwright_stealth import stealth_async
from core.config import USER_DATA_DIR, HEADLESS_MODE, PROXY_SERVER, PROXY_USERNAME, PROXY_PASSWORD

# Resource types to block for bandwidth savings
_BLOCKED_RESOURCE_TYPES = {"image", "media"}


async def _block_unnecessary_requests(route: Route):
    """Blocks images, videos, and fonts to save bandwidth."""
    request = route.request
    
    # Block by resource type
    if request.resource_type in _BLOCKED_RESOURCE_TYPES:
        await route.abort()
        return
    
    await route.continue_()


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
            "--test-type",
            # Essential for headless VPS without GPU/display
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-software-rasterizer",
            # Prevent WebRTC from leaking local IP to LinkedIn when using Proxy
            "--disable-features=WebRtcHideLocalIpsWithMdns",
        ]

        proxy_config = None
        if PROXY_SERVER:
            proxy_config = {
                "server": PROXY_SERVER,
            }
            if PROXY_USERNAME and PROXY_PASSWORD:
                proxy_config["username"] = PROXY_USERNAME
                proxy_config["password"] = PROXY_PASSWORD
            print(f"[Browser] Using proxy: {PROXY_SERVER}")

        # Prepare userdata dir
        os.makedirs(USER_DATA_DIR, exist_ok=True)

        # In headless mode (VPS), set a fixed viewport — LinkedIn's SPA needs
        # viewport dimensions to trigger lazy loading and render job cards.
        # In headed mode (local dev), use no_viewport so browser fills the screen.
        viewport_config = {"width": 1920, "height": 1080} if HEADLESS_MODE else None

        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        self._browser_context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=HEADLESS_MODE,
            args=launch_args,
            ignore_default_args=["--enable-automation", "--disable-extensions"],
            proxy=proxy_config,
            viewport=viewport_config,
            no_viewport=not HEADLESS_MODE,
            user_agent=user_agent,
            record_video_dir=None
        )

        # Get primary page
        pages = self._browser_context.pages
        self._page = pages[0] if pages else await self._browser_context.new_page()

        # Apply stealth
        await stealth_async(self._page)
        
        # Ensure viewport is set (critical for headless — LinkedIn won't render without it)
        if HEADLESS_MODE:
            await self._page.set_viewport_size({"width": 1920, "height": 1080})
        
        # Increase timeouts for proxy connections (residential proxies are slower)
        self._browser_context.set_default_navigation_timeout(60000)  # 60s for page loads
        self._browser_context.set_default_timeout(45000)  # 45s for element waits
        
        return self._page

    async def enable_bandwidth_saver(self):
        """Bandwidth saver disabled to ensure 100% identical rendering to local."""
        print("[Browser] Bandwidth saver is disabled. Loading all resources (CSS, Images, etc) normally.")
        pass

    async def fresh_page(self) -> Page:
        """Opens a new tab, closing the old one. Resets LinkedIn's SPA JavaScript
        state while preserving cookies/session. Needed after login check on /feed
        contaminates the Ember.js SPA state in headless mode."""
        if self._page:
            await self._page.close()
        self._page = await self._browser_context.new_page()
        await stealth_async(self._page)
        if HEADLESS_MODE:
            await self._page.set_viewport_size({"width": 1920, "height": 1080})
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
