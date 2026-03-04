import asyncio
from playwright.async_api import Page, Locator
from browser.stealth import random_sleep, human_type
from ai.form_solver import solve_form

MAX_RETRIES = 3

async def start_easy_apply(page: Page, job_id: str) -> bool:
    """
    Clicks the Easy Apply button and manages the multi-step form process.
    Returns True if successfully applied, False otherwise.
    """
    print(f"[EasyApply] Starting application for job {job_id}")
    
    # Locate Easy Apply button
    # There are multiple possible selectors for the button depending on the variation
    try:
        # Wait for the main container to load before looking for buttons
        await page.wait_for_selector(".job-view-layout, .jobs-details", timeout=10000)
    except Exception:
        pass # If we timeout waiting for layout, still try to find the button

    try:
        # Array of possible locators for Playwright
        locators = [
            page.locator("[data-view-name='job-apply-button']"),
            page.locator("button.jobs-apply-button"),
            page.locator("button.jobs-apply-button--disabled"), # Sometimes we see it, though we'll check it later
            page.locator("button[aria-label*='Easy Apply']"),
            page.locator("button[aria-label*='Candidatura simplificada']"),
            page.locator("button:has-text('Easy Apply')"),
            page.locator("button:has-text('Candidatura simplificada')"),
            page.locator("a[href*='/apply/']")
        ]
        
        button = None
        for loc in locators:
            if await loc.count() > 0:
                # Get the first one that is visible
                for i in range(await loc.count()):
                    el = loc.nth(i)
                    if await el.is_visible():
                        button = el
                        break
            if button:
                break
                
        if not button:
            print(f"[EasyApply] Job {job_id} does not have an Easy Apply button. Dumping HTML to debug_failed_job.html")
            try:
                html = await page.content()
                with open("debug_failed_job.html", "w", encoding="utf-8") as f:
                    f.write(html)
            except Exception as e:
                print(f"[EasyApply] Failed to dump HTML: {e}")
            return False
            
        await random_sleep(1.0, 3.0)
        await button.click()
        await random_sleep(2.0, 4.0)

    except Exception as e:
        print(f"[EasyApply] Error clicking apply button: {e}")
        return False
    
    return await handle_form_loop(page)

async def handle_form_loop(page: Page) -> bool:
    """
    Iterates through the modal steps (Next, Review, Submit) solving fields via AI.
    """
    step = 1
    max_unchanged_steps = 0
    while step < 15: # safety break
        print(f"[EasyApply] Reading Step {step}")
        await random_sleep(1.5, 3.0)
        
        # Check if we reached the final "Submit application"
        submit_locators = [
            page.locator("button[aria-label='Submit application']"),
            page.locator("button[aria-label='Enviar candidatura']"),
            page.locator("button:has-text('Submit')"),
            page.locator("button:has-text('Enviar')")
        ]
        submit_btn = None
        for loc in submit_locators:
            if await loc.count() > 0 and await loc.first.is_visible():
                submit_btn = loc.first
                break

        if submit_btn:
            print("[EasyApply] Final Submit screen reached.")
            # For testing purposes, we might want to click it or just review.
            print(">>> SKIPPING SUBMIT FOR DRY RUN <<<") 
            # In production: await submit_btn.click()
            await random_sleep(2.0, 3.0)
            
            await close_modal(page)
            return True # Pretending success for the dry-run

        # If not submit, we must answer questions and click "Next" or "Review"
        # 1. Extract fields
        extracted_fields = await extract_fields(page)
        
        # 2. If there are inputs that require answers, use AI
        if extracted_fields:
            print(f"[EasyApply] Found {len(extracted_fields)} fields, calling AI...")
            actions = await solve_form(extracted_fields)
            await execute_ai_actions(page, actions)
        
        # 3. Proceed to next step
        next_locators = [
            page.locator("button[aria-label='Continue to next step']"),
            page.locator("button[aria-label='Avançar para a próxima etapa']"),
            page.locator("button:has-text('Next')"),
            page.locator("button:has-text('Avançar')"),
            page.locator("button.artdeco-button--primary:has-text('Avançar')")
        ]
        next_btn = None
        for loc in next_locators:
            if await loc.count() > 0 and await loc.first.is_visible():
                next_btn = loc.first
                break

        review_locators = [
            page.locator("button[aria-label='Review your application']"),
            page.locator("button[aria-label='Revisar sua candidatura']"),
            page.locator("button:has-text('Review')"),
            page.locator("button:has-text('Revisar')")
        ]
        review_btn = None
        for loc in review_locators:
            if await loc.count() > 0 and await loc.first.is_visible():
                review_btn = loc.first
                break
        
        if next_btn:
            await random_sleep(1.0, 2.0)
            await next_btn.click()
            step += 1
            max_unchanged_steps = 0
            continue
            
        if review_btn:
            await random_sleep(1.0, 2.0)
            await review_btn.click()
            step += 1
            max_unchanged_steps = 0
            continue

        # If no buttons are visible, maybe we got an error in the form
        err_msg = page.locator(".artdeco-inline-feedback--error")
        if await err_msg.count() > 0 and await err_msg.first.is_visible():
            print("[EasyApply] Form Error detected. Aborting application.")
            await close_modal(page)
            return False
            
        max_unchanged_steps += 1
        if max_unchanged_steps > 2:
            print("[EasyApply] Stuck on step. Can't find Next, Review or Submit buttons. Aborting.")
            await close_modal(page)
            return False

    return False

async def extract_fields(page: Page) -> list:
    """Scrapes the current modal step for inputs (text, select, radio)."""
    fields = []
    
    # Wait for form elements
    form_items = await page.locator(".jobs-easy-apply-form-section__grouping").all()
    
    for item in form_items:
        try:
            label = await item.locator("label").first.inner_text()
            
            # Text inputs
            inputs = await item.locator("input[type='text'], input[type='numeric']").all()
            if inputs:
                for inp in inputs:
                    tag_id = await inp.get_attribute("id")
                    fields.append({"selector": f"#{tag_id}", "label": label.strip(), "type": "input", "options": []})
                continue
                
            # Select dropdowns
            selects = await item.locator("select").all()
            if selects:
                for sel in selects:
                    tag_id = await sel.get_attribute("id")
                    options = await sel.locator("option").all_inner_texts()
                    clean_opts = [o.strip() for o in options if o.strip() and o.lower() != "select an option"]
                    fields.append({"selector": f"#{tag_id}", "label": label.strip(), "type": "select", "options": clean_opts})
                continue
                
            # Radio buttons
            radios = await item.locator("fieldset").all()
            if radios:
                for rad in radios:
                    legend = await rad.locator("legend").inner_text()
                    radio_inputs = await rad.locator("input[type='radio']").all()
                    opts = []
                    for r_in in radio_inputs: # We need the IDs and the labels attached to them
                        r_id = await r_in.get_attribute("id")
                        r_lbl = await page.locator(f"label[for='{r_id}']").inner_text()
                        opts.append({"selector": f"#{r_id}", "label": r_lbl.strip()})
                        
                    fields.append({"selector": "fieldset", "label": legend.strip(), "type": "radio", "options": opts})
                continue
                
        except Exception as e:
            # Skip element if it causes trouble parsing
            pass
            
    return fields

async def execute_ai_actions(page: Page, actions: list):
    """Executes the Playwright actions determined by the GPT model."""
    for action in actions:
        selector = action.get("selector")
        act_type = action.get("action")
        val = action.get("value")
        
        if not selector: continue
        
        try:
            el = page.locator(selector)
            if not await el.is_visible():
                continue
                
            if act_type == "type" and val:
                # Clear existing text first
                await el.fill("")
                await human_type(page, selector, str(val))
            elif act_type == "select" and val:
                await el.select_option(label=str(val))
                await random_sleep(0.5, 1.0)
            elif act_type == "click":
                # Used for clicking radio buttons
                await el.click(force=True)
                await random_sleep(0.5, 1.0)
        except Exception as e:
            print(f"[EasyApply] Error executing AI action on {selector}: {e}")

async def close_modal(page: Page):
    """Helper to close the modal and confirm discard."""
    print("[EasyApply] Dismissing modal.")
    close_btn = page.locator("button.artdeco-modal__dismiss, button[aria-label='Dismiss'], button[aria-label='Fechar']")
    if await close_btn.count() > 0 and await close_btn.first.is_visible():
        await close_btn.first.click()
        await random_sleep(1.0, 2.0)
        disc_btn = page.locator("button[data-control-name='discard_application_confirm_btn'], button:has-text('Descartar')")
        if await disc_btn.count() > 0 and await disc_btn.first.is_visible():
            await disc_btn.first.click()
