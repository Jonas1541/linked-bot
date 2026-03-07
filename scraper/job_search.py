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
    # Force a hard parse instead of letting LinkedIn's Ember.js SPA route handle it.
    # In headless Chrome on VPS, the SPA router gets stuck on the loading logo.
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
    
    import re
    
    try:
        # Wait a few seconds for the initial HTML to load at least
        await random_sleep(2.0, 4.0)
        
        # In headless VPS the Ember.js SPA might get stuck on the loading logo
        # but the actual job IDs are already embedded in the raw HTML payload 
        # from the server (inside <code> blocks or initial JSON state).
        # So we bypass the DOM entirely and extract them with regex.
        html_content = await page.content()
        
        # Look for typical job ID patterns in the raw HTML
        # e.g. urn:li:fsd_jobPosting:4376200323 or data-job-id="4376200323"
        pattern1 = r'urn:li:fsd_jobPosting:(\d{10})'
        pattern2 = r'data-job-id="(\d{10})"'
        pattern3 = r'data-occludable-job-id="(\d{10})"'
        
        matches = []
        matches.extend(re.findall(pattern1, html_content))
        matches.extend(re.findall(pattern2, html_content))
        matches.extend(re.findall(pattern3, html_content))
        
        # Deduplicate and maintain order
        for j_id in matches:
            if j_id not in job_ids:
                job_ids.append(j_id)
                
        print(f"[Search] Extracted {len(job_ids)} raw job IDs from HTML source.")
                
    except Exception as e:
        print(f"[Search] Error extracting job IDs: {e}")
        
    return job_ids
