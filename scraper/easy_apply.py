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

    job_description = ""
    try:
        job_desc_loc = page.locator(".jobs-description-content__text, #job-details, .job-details-jobs-unified-top-card__job-insight")
        if await job_desc_loc.count() > 0:
            job_description = (await job_desc_loc.first.inner_text())[:4000]
    except Exception:
        pass

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
    
    return await handle_form_loop(page, job_description)

async def handle_form_loop(page: Page, job_description: str = "") -> bool:
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
            if not job_description:
                print(f"[EasyApply] Warning: Extracting Job Description failed previously. AI might miss language context.")
            print(f"[EasyApply] Found {len(extracted_fields)} fields, calling AI...")
            
            actions = await solve_form(extracted_fields, job_description=job_description)
            
            # DEBUG LOG
            with open("ai_form_debug.log", "a", encoding="utf-8") as f:
                import json
                f.write(f"\n--- STEP {step} ---\nINPUT FIELDS:\n{json.dumps(extracted_fields, indent=2)}\nACTIONS:\n{json.dumps(actions, indent=2)}\n")
            
            await execute_ai_actions(page, actions)
        
        # Check if we got an error in the form from previous actions before we try to click next again
        # We need to wait a tiny bit to see if an error appears
        await random_sleep(1.0, 1.5)
        err_msg = page.locator(".artdeco-inline-feedback--error")
        if await err_msg.count() > 0 and await err_msg.first.is_visible():
            err_text = await err_msg.first.inner_text()
            print(f"[EasyApply] Form Error detected: '{err_text}'. Aborting application.")
            await close_modal(page)
            return False

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
            
        max_unchanged_steps += 1
        if max_unchanged_steps > 2:
            print("[EasyApply] Stuck on step. Can't find Next, Review or Submit buttons. Aborting.")
            await close_modal(page)
            return False

    return False

async def extract_fields(page: Page) -> list:
    """Scrapes the current modal step for inputs, selects, and radios without depending on brittle container classes."""
    fields = []
    
    # Restrict our search to avoid grabbing hidden inputs outside the form modal view
    modal = page.locator(".pb4, .jobs-easy-apply-modal, .artdeco-modal").first
    if await modal.count() == 0:
        return fields
        
    # 1. Text Inputs / Selects / Textareas
    elements = await modal.locator("input[type='text'], input[type='numeric'], input[type='number'], input[type='email'], input[type='tel'], select, textarea").all()
    for el in elements:
        try:
            if not await el.is_visible():
                continue
            
            tag_name = await el.evaluate("e => e.tagName.toLowerCase()")
            tag_id = await el.get_attribute("id")
            
            label = ""
            if tag_id:
                label_loc = modal.locator(f"label[for='{tag_id}']")
                if await label_loc.count() > 0:
                    label = await label_loc.first.inner_text()
            
            if not label:
                parent_label = await el.evaluate("e => e.closest('label') ? e.closest('label').innerText : ''")
                if parent_label:
                    label = parent_label
                    
            if not label:
                continue
                
            label = label.strip()
            
            if tag_name == "select":
                options = await el.locator("option").all_inner_texts()
                clean_opts = [o.strip() for o in options if o.strip() and o.lower() != "select an option"]
                fields.append({"selector": f"[id='{tag_id}']", "label": label, "type": "select", "options": clean_opts})
            else:
                fields.append({"selector": f"[id='{tag_id}']", "label": label, "type": "input", "options": []})
        except Exception:
            pass

    # 2. Radio Button Groups (Fieldsets or loose)
    fieldsets = await modal.locator("fieldset").all()
    for fs in fieldsets:
        try:
            if not await fs.is_visible():
                continue
                
            legend_loc = fs.locator("legend")
            legend = await legend_loc.inner_text() if await legend_loc.count() > 0 else "Radio Group"
            legend = legend.strip()
            
            radio_inputs = await fs.locator("input[type='radio']").all()
            if not radio_inputs:
                continue
                
            opts = []
            for r_in in radio_inputs:
                r_id = await r_in.get_attribute("id")
                r_lbl_loc = modal.locator(f"label[for='{r_id}']")
                if await r_lbl_loc.count() > 0:
                    r_lbl = await r_lbl_loc.inner_text()
                else:
                    r_lbl = await fs.locator(f"[for='{r_id}']").inner_text() if await fs.locator(f"[for='{r_id}']").count() > 0 else r_id
                opts.append({"selector": f"[id='{r_id}']", "label": r_lbl.strip()})
                
            fields.append({"selector": "fieldset", "label": legend, "type": "radio", "options": opts})
        except Exception:
            pass

    # 3. Solo Checkboxes
    checkboxes = await modal.locator("input[type='checkbox']").all()
    for cb in checkboxes:
        try:
            if not await cb.is_visible():
                continue
            cb_id = await cb.get_attribute("id")
            if cb_id:
                label_loc = modal.locator(f"label[for='{cb_id}']")
                label = await label_loc.inner_text() if await label_loc.count() > 0 else "Checkbox"
                fields.append({"selector": f"[id='{cb_id}']", "label": label.strip(), "type": "checkbox", "options": []})
        except Exception:
            pass
            
    # 4. Resume Selection Container
    resume_containers = await modal.locator(".jobs-document-upload-redesign-card__container").all()
    if resume_containers:
        opts = []
        for rc in resume_containers:
            inputs = await rc.locator("input[type='radio']").all()
            for r_in in inputs:
                r_id = await r_in.get_attribute("id")
                card = modal.locator(f"label[for='{r_id}']")
                if await card.count() > 0:
                    name = await card.inner_text()
                    opts.append({"selector": f"[id='{r_id}']", "label": name.strip()})
        if opts:
            fields.append({"selector": "resume_radios", "label": "Choose resume / Escolha o currículo", "type": "radio", "options": opts})

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
            if await el.count() == 0:
                continue

            if act_type == "type" and val:
                # Clear existing text first
                await el.fill("")
                await human_type(page, selector, str(val))
                
                # Check for location/autocomplete dropdowns that might block the "Next" button
                await random_sleep(1.0, 2.0)
                typeahead = page.locator(".search-typeahead-v2__hit, .jobs-search-box__typeahead-suggestion")
                if await typeahead.count() > 0 and await typeahead.first.is_visible():
                    # Press ArrowDown and Enter to select the first autocomplete option
                    await page.keyboard.press("ArrowDown")
                    await random_sleep(0.5, 1.0)
                    await page.keyboard.press("Enter")
                    await random_sleep(0.5, 1.0)
            elif act_type == "select" and val:
                await el.select_option(label=str(val))
                await random_sleep(0.5, 1.0)
            elif act_type == "click":
                # For radio buttons/checkboxes, React often intercepts clicks on the pseudo-hidden input
                # It's more reliable to click the `<label>` linked to it.
                # Handle the edge case where the AI returns "fieldset" as selector + text value
                # instead of returning the specific option's selector.
                tag_name = await el.evaluate("e => e.tagName.toLowerCase()")
                if tag_name == "fieldset" and (act_type == "click" or act_type == "select") and val:
                    val_str = str(val)
                    if val_str.startswith("[id="):
                        # The AI put the option's selector inside the 'value' field!
                        opt_id = val_str.replace("[id='", "").replace("']", "")
                        lbl = page.locator(f"label[for='{opt_id}']")
                        if await lbl.count() > 0:
                            await lbl.first.click(force=True)
                            await random_sleep(0.5, 1.0)
                            continue
                    else:
                        # Find the label inside the fieldset that matches the value text
                        matching_labels = await el.locator(f"label:has-text('{val_str}')").all()
                        if matching_labels:
                            await matching_labels[0].click(force=True)
                            await random_sleep(0.5, 1.0)
                            continue
                        
                if tag_name == "input":
                    input_id = await el.get_attribute("id")
                    if input_id:
                        lbl = page.locator(f"label[for='{input_id}']")
                        if await lbl.count() > 0:
                            await lbl.first.click(force=True)
                            await random_sleep(0.5, 1.0)
                            continue
                
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
