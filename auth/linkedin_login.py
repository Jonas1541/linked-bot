import pyotp
import asyncio
from playwright.async_api import Page, expect
from core.config import LINKEDIN_USERNAME, LINKEDIN_PASSWORD, LINKEDIN_2FA_SECRET
from browser.stealth import human_type, random_sleep

async def is_logged_in(page: Page) -> bool:
    """Checks if the current session is valid by navigating to the homepage and looking for the feed."""
    print("[Auth] Checking login status...")
    await page.goto("https://www.linkedin.com/feed/")
    try:
        await expect(page.locator("id=global-nav")).to_be_visible(timeout=15000)
        print("[Auth] Session is valid. User is already logged in!")
        return True
    except Exception:
        # Fallback: if LinkedIn redirected us to /feed, we're logged in even if global-nav didn't render yet
        if "/feed" in page.url:
            print("[Auth] Session is valid (URL confirms /feed). User is already logged in!")
            return True
        print("[Auth] Session invalid or expired. Need to login.")
        return False

async def perform_login(page: Page):
    """Executes the complete login flow including 2FA if configured."""
    # First, check if we are already logged in from a previous session
    if await is_logged_in(page):
        return True

    if not LINKEDIN_USERNAME or not LINKEDIN_PASSWORD:
        raise ValueError("Missing LinkedIn credentials in .env")

    print("[Auth] Navigating to login page...")
    await page.goto("https://www.linkedin.com/login")
    await random_sleep(2.0, 4.0)

    # Fill username and password with human behavior
    print("[Auth] Typing credentials...")
    try:
        await page.wait_for_selector("id=username", timeout=30000)
    except Exception:
        # Dump the page to see what LinkedIn is showing (CAPTCHA? challenge?)
        html = await page.content()
        with open("debug_login_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[Auth] Login page did not render username field! HTML dumped to debug_login_page.html ({len(html)} bytes)")
        print(f"[Auth] Page URL: {page.url}")
        print(f"[Auth] Page title: {await page.title()}")
        return False
    
    await human_type(page, "id=username", LINKEDIN_USERNAME)
    await random_sleep(0.5, 1.5)
    await human_type(page, "id=password", LINKEDIN_PASSWORD)
    
    await random_sleep(1.0, 2.0)
    print("[Auth] Clicking sign in...")
    await page.click("button[type='submit']")

    # Check for 2FA Request
    await random_sleep(3.0, 5.0)
    
    # Check if it's the push notification screen (asking to check phone)
    if await page.locator("text='Abra seu aplicativo LinkedIn'").count() > 0 or await page.locator("text='Open your LinkedIn app'").count() > 0 or await page.locator("button#button__use-another-method").count() > 0:
        print("[Auth] Push notification 2FA detected. Attempting to switch to Authenticator App code...")
        
        # Click the "Try another way" or "Use another method" link to select TOTP
        try:
            # Usually it's a button or link to choose another method
            if await page.locator("button#button__use-another-method").count() > 0:
                await page.click("button#button__use-another-method")
                await random_sleep(1.0, 2.0)
                
            # Then click the specific option for Authenticator App
            # The exact text might vary, we look for 'Authenticator' or 'MFA'
            auth_app_btn = page.locator("button:has-text('Authenticator'), button:has-text('Autenticador')").first
            if await auth_app_btn.count() > 0:
                await auth_app_btn.click()
                await random_sleep(1.0, 2.0)
        except Exception as e:
            print(f"[Auth] Could not automatically switch to Authenticator app: {e}")
            print("[Auth] Waiting 30s for you to approve on your phone manually or switch manually...")
            await page.wait_for_timeout(30000)

    # Now check if we are at the PIN input screen
    if await page.locator("input[name='pin']").count() > 0 or await page.locator("input#input__email_verification_pin").count() > 0:
        print("[Auth] 2FA PIN required!")
        if not LINKEDIN_2FA_SECRET:
            print("[Auth] ERROR: 2FA required but LINKEDIN_2FA_SECRET is not configured.")
            return False

        print("[Auth] Generating OTP...")
        totp = pyotp.TOTP(LINKEDIN_2FA_SECRET)
        code = totp.now()

        # Try to locate the pin field
        pin_selector = "input[name='pin']" if await page.locator("input[name='pin']").count() > 0 else "input#input__email_verification_pin"

        await human_type(page, pin_selector, code)
        await random_sleep(1.0, 2.0)
        print("[Auth] Submitting OTP...")
        # Handle different variations of the submit button
        submit_btn = page.locator("button#verify-pin-submit-button, button#two-step-submit-button, button[type='submit']")
        if await submit_btn.count() > 0:
            await submit_btn.first.click()

        await random_sleep(5.0, 8.0) # Wait for login sequence to finalize
    else:
        # If no PIN field is visible, it might be waiting for the push notification to be approved
        print("[Auth] No PIN field detected. If it's waiting for a push notification, please approve it on your phone.")
        # Wait up to 30 seconds for manual approval or redirect
        try:
            await expect(page.locator("id=global-nav")).to_be_visible(timeout=30000)
        except Exception:
            pass

    return await is_logged_in(page)
