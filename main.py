import asyncio
from core.config import USER_PROFILE, MAX_DAILY_APPLICATIONS
from database.db_manager import db
from browser.session import BrowserManager
from auth.linkedin_login import perform_login
from scraper.job_search import perform_search, extract_job_ids_from_page
from scraper.easy_apply import start_easy_apply
from browser.stealth import random_sleep

async def main_loop():
    print("====================================")
    print("      LinkedIn Auto-Applier Bot     ")
    print("====================================")
    
    # 1. Check daily limit right away
    applied_today = db.get_daily_application_count()
    if applied_today >= MAX_DAILY_APPLICATIONS:
        print(f"[Main] Daily limit reached ({applied_today}/{MAX_DAILY_APPLICATIONS}). Exiting.")
        return

    # 2. Init Browser
    browser_manager = BrowserManager()
    page = await browser_manager.init_browser()
    
    try:
        # 3. Handle Authentication
        authenticated = await perform_login(page)
        if not authenticated:
            print("[Main] Failed to authenticate. Exiting.")
            return

        print("[Main] Logged in successfully.")

        # 4. Search and Process Jobs Loop
        # We grab parameters from user profile (e.g., job titles)
        keywords = USER_PROFILE.get("preferences", {}).get("roles", ["Software Engineer"])[0]
        location = USER_PROFILE.get("personal_info", {}).get("location", "Brazil")
        
        # In a robust scenario we'd loop through multiple pages (start_index = 0, 25, 50...)
        # Here we do a single page for demonstration
        await perform_search(page, keywords, location, start_index=0)
        await random_sleep(2.0, 4.0)

        job_ids = await extract_job_ids_from_page(page)
        print(f"[Main] Found {len(job_ids)} jobs on this page.")

        for job_id in job_ids:
            # Check limit before each execution
            if db.get_daily_application_count() >= MAX_DAILY_APPLICATIONS:
                print("[Main] Daily limit reached midway. Stopping.")
                break
                
            # Skip if already applied/failed
            if db.is_job_applied(job_id):
                print(f"[Main] Skipping job {job_id}, already processed.")
                continue
                
            # Navigate to the specific job page
            job_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
            print(f"[Main] Navigating to job {job_url}")
            try:
                await page.goto(job_url)
                await random_sleep(2.0, 4.0)
            except Exception as e:
                print(f"[Main] Could not load job page: {e}")
                continue

            # 5. Execute Apply Flow
            success = await start_easy_apply(page, job_id)
            
            # 6. Save State  
            # 'APPLIED' if it went through the steps and clicked submit (simulated as success inside dry-run right now)
            # 'FAILED' if it crashed or didn't have Easy Apply
            status_text = "APPLIED" if success else "FAILED"
            db.add_application(job_id, title="ExtractTitleLater", company="ExtractCompanyLater", status=status_text)
            
            # 7. Global Pacing / Rate Limiter
            # High delays to mimic a human looking at different things. Wait 1-3 minutes.
            if success:
                print(f"[Main] Successfully processed job {job_id}. Taking a long breather...")
                await random_sleep(60.0, 180.0) 
            else:
                print(f"[Main] Failed to process job {job_id}. Moving to next.")
                await random_sleep(5.0, 15.0)

    except Exception as e:
        print(f"[Main] Unhandled exception occurred: {e}")
    finally:
        print("[Main] Shutting down browser...")
        await browser_manager.close()

if __name__ == "__main__":
    asyncio.run(main_loop())
