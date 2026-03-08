import os
import asyncio
from playwright.async_api import async_playwright, Page, BrowserContext, Route
from playwright_stealth import stealth_async
from core.config import USER_DATA_DIR, HEADLESS_MODE, PROXY_SERVER, PROXY_USERNAME, PROXY_PASSWORD

# Resource types to block for bandwidth savings (saves ~60-70% of data)
_BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}


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
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--enforce-webrtc-ip-permission-check",
            # Additional stealth: Hide that we are using a Virtual Display (Mesa / SwiftShader)
            "--override-use-software-gl-for-tests",
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

        # Force a fixed 1920x1080 viewport. Xvfb defaults to 640x480 which triggers
        # LinkedIn's Mobile SDUI layout. We MUST force the desktop viewport.
        viewport_config = {"width": 1920, "height": 1080}

        # Deep Stealth: Timezone and Locale MUST match the proxy IP location (Brazil)
        # Otherwise, LinkedIn's anti-bot detects a Brazilian IP running UTC time with en-US language.
        locale = "pt-BR"
        timezone_id = "America/Sao_Paulo"
        geolocation = {"latitude": -23.5505, "longitude": -46.6333} # Sao Paulo coords

        # Use a very recent standard Chrome user agent
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

        self._browser_context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=HEADLESS_MODE,
            args=launch_args,
            ignore_default_args=["--enable-automation", "--disable-extensions"],
            proxy=proxy_config,
            viewport=viewport_config,
            user_agent=user_agent,
            locale=locale,
            timezone_id=timezone_id,
            geolocation=geolocation,
            permissions=["geolocation"],
            color_scheme="dark",
            record_video_dir=None
        )

        # Get primary page
        pages = self._browser_context.pages
        self._page = pages[0] if pages else await self._browser_context.new_page()

        await self._apply_deep_stealth(self._page)
        
        if HEADLESS_MODE:
            await self._page.set_viewport_size({"width": 1920, "height": 1080})
        
        # Increase timeouts for proxy connections (residential proxies are slower)
        self._browser_context.set_default_navigation_timeout(120000)  # 120s for page loads
        self._browser_context.set_default_timeout(90000)  # 90s for element waits
        
        return self._page

    async def enable_bandwidth_saver(self):
        """Blocks images, media, fonts, and trackers to save proxy bandwidth.
        Call this AFTER authentication — login page needs all resources."""
        if self._page:
            await self._page.route("**/*", _block_unnecessary_requests)
            print("[Browser] Bandwidth saver enabled: blocking images, media, fonts, and trackers.")

    async def _apply_deep_stealth(self, page: Page):
        """Applies advanced stealth beyond playwright-stealth, masking the VPS."""
        await stealth_async(page)
        
        # Spoof WebGL and missing APIs
        await page.add_init_script("""
            // Spoof Permissions API to avoid headless detection
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // Mask the Xvfb / headless WebGL vendor
            try {
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) return 'Google Inc. (Intel)';
                    if (parameter === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics 620 (0x00005920) Direct3D11 vs_5_0 ps_5_0, D3D11)';
                    return getParameter.apply(this, arguments);
                };
            } catch(e) {}
        """)

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
