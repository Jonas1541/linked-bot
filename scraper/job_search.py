import urllib.parse
from playwright.async_api import Page, expect
from browser.stealth import random_sleep

async def perform_search(page: Page, keywords: str, location: str, start_index: int = 0):
    """
    Constructs the search URL for Jobs on LinkedIn and navigates to it.
    Applies the 'Easy Apply' filter by default (f_AL=true).
    """
    base_url = "https://www.linkedin.com/jobs/search/"
    
    # f_WT=2 is for Remote (Home Office)
    # f_AL=true is for Easy Apply
    params = {
        "keywords": keywords,
        "location": location,
        "f_WT": "2",
        "f_AL": "true", 
        "start": str(start_index)
    }
    
    query_string = urllib.parse.urlencode(params)
    search_url = f"{base_url}?{query_string}"

    print(f"[Search] Navigating to: {search_url}")
    # Reset SPA state — after login check on /feed, LinkedIn's Ember.js does
    # client-side routing which doesn't render properly in headless mode.
    await page.goto("about:blank")
    await page.goto(search_url, wait_until="domcontentloaded")
    
    # Wait for job list to load (longer timeout for proxy connections)
    try:
        await expect(page.locator(".jobs-search-results-list, .scaffold-layout__list, ul.scaffold-layout__list-container")).to_be_visible(timeout=30000)
        await random_sleep(3.0, 5.0)
    except Exception as e:
        print("[Search] Warning: Job list did not load exactly as expected. Trying to proceed anyway.")
        await random_sleep(3.0, 5.0)  # Give extra time anyway
        pass

async def extract_job_ids_from_page(page: Page) -> list[str]:
    """
    Scrolls through the job list panel to load jobs and extracts their IDs.
    """
    job_ids = []
    
    try:
        # Wait for the list container or generic job cards to appear
        try:
            await page.wait_for_selector("div[data-job-id], li[data-occludable-job-id], li.jobs-search-results__list-item", timeout=30000)
        except Exception:
            print("[Search] Timeout waiting for job cards. They might be using a new DOM structure.")
            
        # In modern LinkedIn DOM, job cards might have 'data-job-id' or 'data-occludable-job-id'
        cards = await page.locator("div[data-job-id], li[data-occludable-job-id], li.jobs-search-results__list-item").all()
        
        for idx, card in enumerate(cards):
            job_id = await card.get_attribute("data-job-id")
            if not job_id:
                job_id = await card.get_attribute("data-occludable-job-id")
            
            # Fallback if the element itself doesn't have it, maybe a child does
            if not job_id:
                try:
                    inner_div = card.locator("div[data-job-id]").first
                    if await inner_div.count() > 0:
                        job_id = await inner_div.get_attribute("data-job-id")
                except Exception:
                    pass
                
            if job_id and job_id not in job_ids:
                job_ids.append(job_id)
            
            # Scroll to it to trigger lazy loading of next items
            try:
                await card.scroll_into_view_if_needed()
            except Exception:
                pass
                
            if idx % 5 == 0:
                await random_sleep(0.5, 1.5)
                
    except Exception as e:
        print(f"[Search] Error extracting job IDs: {e}")
        
    return job_ids
