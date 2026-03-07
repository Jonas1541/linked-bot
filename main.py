import asyncio
import random
from core.config import USER_PROFILE
from database.db_manager import db
from browser.session import BrowserManager
from auth.linkedin_login import perform_login
from scraper.job_search import perform_search, extract_job_ids_from_page
from scraper.easy_apply import start_easy_apply
from browser.stealth import random_sleep
from notifications.telegram import notify_run_summary, notify_error

MAX_PAGES = 10  # Safety limit: don't go beyond 10 pages (250 jobs) per run


async def main_loop():
    print("====================================")
    print("      LinkedIn Auto-Applier Bot     ")
    print("====================================")
    
    # 1. Safety check (hard cap — should never hit with 3 cron runs of 12-22)
    applied_today = db.get_daily_application_count()
    if applied_today >= 75:
        print(f"[Main] Safety cap reached ({applied_today} today). Exiting.")
        return

    # 2. Determine today's search keyword (cycles daily through roles)
    roles = USER_PROFILE.get("preferences", {}).get("roles", ["Software Engineer"])
    role_index = db.get_todays_role_index(len(roles))
    keywords = roles[role_index]
    location = USER_PROFILE.get("personal_info", {}).get("location", "Brazil")
    
    # Randomize per-run limit for organic behavior (avoids always applying to exactly N)
    max_apps_this_run = random.randint(12, 22)
    
    print(f"[Main] Today's search role: '{keywords}' (index {role_index}/{len(roles)-1})")
    print(f"[Main] All roles: {roles}")
    print(f"[Main] Applications today so far: {applied_today}")
    print(f"[Main] This run limit: {max_apps_this_run}")

    # 3. Init Browser
    browser_manager = BrowserManager()
    page = await browser_manager.init_browser()
    
    try:
        # 4. Handle Authentication
        authenticated = await perform_login(page)
        if not authenticated:
            print("[Main] Failed to authenticate. Exiting.")
            return

        print("[Main] Logged in successfully.")
        
        # Open a fresh page to reset LinkedIn's SPA state from the /feed login check.
        # The /feed page initializes Ember.js which breaks search rendering in headless.
        page = await browser_manager.fresh_page()
        
        # Enable bandwidth saving on the fresh page
        await browser_manager.enable_bandwidth_saver()

        # 5. Multi-page search loop
        total_applied = 0
        total_skipped = 0
        total_failed = 0
        
        for page_num in range(MAX_PAGES):
            start_index = page_num * 25
            
            print(f"\n[Main] === Searching page {page_num + 1} (offset {start_index}) ===")
            await perform_search(page, keywords, location, start_index=start_index)
            await random_sleep(2.0, 4.0)

            job_ids = await extract_job_ids_from_page(page)
            print(f"[Main] Found {len(job_ids)} jobs on page {page_num + 1}.")
            
            if not job_ids:
                print("[Main] No more jobs found. Search exhausted.")
                break

            new_jobs_on_page = 0
            
            for job_id in job_ids:
                # Check per-run limit
                if total_applied >= max_apps_this_run:
                    print(f"[Main] Per-run limit reached ({max_apps_this_run}). Saving the rest for later.")
                    break
                    
                # Skip if already applied/failed
                if db.is_job_applied(job_id):
                    total_skipped += 1
                    continue
                
                new_jobs_on_page += 1
                    
                # Navigate to the specific job page
                job_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
                print(f"[Main] Navigating to job {job_url}")
                try:
                    await page.goto(job_url, wait_until="domcontentloaded")
                    await random_sleep(2.0, 4.0)
                except Exception as e:
                    print(f"[Main] Could not load job page: {e}")
                    continue

                # Execute Apply Flow
                success = await start_easy_apply(page, job_id)
                
                # Save State
                status_text = "APPLIED" if success else "FAILED"
                db.add_application(job_id, title="", company="", status=status_text)
                
                if success:
                    total_applied += 1
                    print(f"[Main] ✓ Successfully applied to job {job_id}. Taking a breather...")
                    await random_sleep(60.0, 180.0)
                else:
                    total_failed += 1
                    print(f"[Main] ✗ Failed to apply to job {job_id}. Moving to next.")
                    await random_sleep(5.0, 15.0)
            
            # Check if we hit the per-run limit
            if total_applied >= max_apps_this_run:
                print(f"[Main] Per-run limit reached. Stopping pagination.")
                break
            
            # If all jobs on this page were already processed, the next page might also be stale
            if new_jobs_on_page == 0:
                print(f"[Main] All jobs on page {page_num + 1} were already processed. Moving to next page...")
            
            # Small delay between pages
            await random_sleep(3.0, 6.0)

        # 6. Summary
        total_today = db.get_daily_application_count()
        print("\n====================================")
        print("         Session Summary            ")
        print("====================================")
        print(f"  Search keyword:  {keywords}")
        print(f"  Pages scanned:   {page_num + 1}")
        print(f"  Applied:         {total_applied}")
        print(f"  Failed:          {total_failed}")
        print(f"  Skipped (dupes): {total_skipped}")
        print(f"  Total today:     {total_today}")
        print("====================================")
        
        # 7. Telegram notification
        await notify_run_summary(keywords, page_num + 1, total_applied, total_failed, total_skipped, total_today)

    except Exception as e:
        print(f"[Main] Unhandled exception occurred: {e}")
        await notify_error(str(e))
    finally:
        print("[Main] Shutting down browser...")
        await browser_manager.close()

if __name__ == "__main__":
    asyncio.run(main_loop())
