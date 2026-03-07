import asyncio
from playwright.async_api import Page, Locator
from browser.stealth import random_sleep, human_type
from ai.form_solver import solve_form
from core.config import PROXY_SERVER

MAX_RETRIES = 3

# English indicator words (common in job descriptions AND job titles)
_EN_WORDS = {"the", "and", "you", "with", "for", "are", "will", "our", "this", "your",
             "experience", "team", "about", "work", "role", "skills", "we", "requirements",
             "looking", "join", "company", "position", "responsibilities", "including",
             "ability", "knowledge", "development", "software", "engineering",
             "developer", "engineer", "senior", "junior", "backend", "frontend",
             "fullstack", "full-stack", "remote", "lead", "architect", "manager",
             "analyst", "specialist", "consultant", "java", "python", "node"}

# Portuguese indicator words (common in job descriptions AND job titles)
_PT_WORDS = {"você", "com", "para", "são", "nossa", "equipe", "sobre", "vaga", "experiência",
             "requisitos", "empresa", "responsabilidades", "conhecimento", "trabalho",
             "desenvolvimento", "buscamos", "procuramos", "nosso", "atuação", "oportunidade",
             "candidato", "atividades", "desejável", "necessário", "formação", "superior",
             "desenvolvedor", "engenheiro", "pleno", "sênior", "júnior", "analista",
             "remoto", "especialista", "consultor", "coordenador", "gerente"}


def detect_language(text: str) -> str:
    """Detects whether `text` is primarily English or Portuguese using word frequency.
    Returns 'en' or 'pt'. Defaults to 'pt' (user's native language) if uncertain."""
    if not text:
        return "pt"
    words = set(text.lower().split())
    en_score = len(words & _EN_WORDS)
    pt_score = len(words & _PT_WORDS)
    detected = "en" if en_score > pt_score else "pt"
    print(f"[EasyApply] Language detection: EN={en_score}, PT={pt_score} -> {detected}")
    return detected


async def handle_resume_selection(page: Page, job_title: str, job_description: str):
    """Deterministically selects the correct resume based on JOB TITLE language.
    Uses ONLY the title for language detection (description has PT UI noise).
    This runs BEFORE the AI, directly in Playwright."""
    modal = page.locator(".artdeco-modal__content, .jobs-easy-apply-modal")
    if await modal.count() == 0:
        return

    resume_containers = await modal.first.locator(".jobs-document-upload-redesign-card__container").all()
    if not resume_containers:
        return

    # Build a map of resume options
    options = []
    for rc in resume_containers:
        inputs = await rc.locator("input[type='radio']").all()
        for r_in in inputs:
            r_id = await r_in.get_attribute("id")
            card = modal.first.locator(f"label[for='{r_id}']")
            if await card.count() > 0:
                label_text = await card.inner_text()
                options.append({"id": r_id, "label": label_text.strip()})

    if not options:
        return

    # Use ONLY the job title for language detection (it's never contaminated by LinkedIn PT UI)
    lang = detect_language(job_title)
    target_keyword = "Resume.pdf" if lang == "en" else "Curriculo.pdf"

    # Debug log to file
    with open("ai_form_debug.log", "a", encoding="utf-8") as f:
        f.write(f"\n--- RESUME SELECTION ---\nJob Title: {job_title}\nDetected Language: {lang}\nTarget: {target_keyword}\nOptions: {[o['label'] for o in options]}\n")

    print(f"[EasyApply] Resume selection: lang={lang}, looking for '{target_keyword}' among {len(options)} options")

    for opt in options:
        if target_keyword in opt["label"]:
            if "Desmarcar" in opt["label"] or "Deselect" in opt["label"]:
                print(f"[EasyApply] Resume '{target_keyword}' is ALREADY selected. No action needed.")
                return
            else:
                print(f"[EasyApply] Clicking resume: {opt['label']}")
                lbl = page.locator(f"label[for='{opt['id']}']")
                if await lbl.count() > 0:
                    await lbl.first.click(force=True)
                    await random_sleep(0.5, 1.0)
                return

    print(f"[EasyApply] WARNING: Could not find resume matching '{target_keyword}'. Options: {[o['label'] for o in options]}")


async def start_easy_apply(page: Page, job_id: str) -> bool:
    """
    Clicks the Easy Apply button and manages the multi-step form process.
    Returns True if successfully applied, False otherwise.
    """
    print(f"[EasyApply] Starting application for job {job_id}")
    
    # Locate Easy Apply button
    # There are multiple possible selectors for the button depending on the variation
    try:
        # Force a hard parse to bypass the Ember.js router freeze if coming from search
        await page.goto("about:blank")
        
        job_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
        # We only wait for DOM, not networkidle, to save RAM
        await page.goto(job_url, wait_until="domcontentloaded", timeout=45000)
        
        # Aggressively stop page loading to prevent Ember.js from eating all 1GB RAM on the VPS
        try:
            await page.evaluate("window.stop();")
        except Exception:
            pass
            
        # Wait for the main container or title, but don't strictly fail on timeout
        try:
            await page.wait_for_selector("h1, .jobs-unified-top-card, .job-view-layout, .jobs-details", timeout=15000)
        except Exception:
            print(f"[EasyApply] Warning: Job {job_id} container check timed out, but proceeding anyway.")
            
    except Exception as e:
        print(f"[EasyApply] Critical Timeout: Job {job_id} failed to reach DOM: {e}")
        return False
        
    job_description = ""
    try:
        # Wait for page content to load
        await random_sleep(1.5, 2.5)
        
        # STEP 1: ALWAYS grab the job title first (it's never hidden behind "See more")
        # Use document.title which ALWAYS contains the job title on LinkedIn (e.g. "Software Engineer | Company | LinkedIn")
        title_text = ""
        try:
            raw_title = await page.title()
            if raw_title:
                # LinkedIn page titles are like: "Job Title | Company Name | LinkedIn" or "(N) Job Title | Company | LinkedIn"
                # Strip notification count prefix like "(3) "
                clean = raw_title.strip()
                if clean.startswith("(") and ")" in clean:
                    clean = clean[clean.index(")") + 1:].strip()
                # Take first segment before " | "
                if " | " in clean:
                    title_text = clean.split(" | ")[0].strip()
                elif " - " in clean:
                    title_text = clean.split(" - ")[0].strip()
                else:
                    title_text = clean
                print(f"[EasyApply] Job title from page title: '{title_text}'")
        except Exception:
            pass

        # Fallback: try CSS selectors if document.title failed
        if not title_text:
            title_selectors = [
                "h1.top-card-layout__title",
                "h1.t-24",
                "h1.job-details-jobs-unified-top-card__job-title",
                ".jobs-unified-top-card__job-title",
                "h1"
            ]
            for ts in title_selectors:
                try:
                    t_loc = page.locator(ts)
                    if await t_loc.count() > 0:
                        title_text = (await t_loc.first.inner_text()).strip()
                        if title_text:
                            print(f"[EasyApply] Job title found via CSS '{ts}': '{title_text}'")
                            break
                except Exception:
                    pass
        
        # STEP 2: Try to expand and read the full description
        see_more_selectors = [
            "button.jobs-description__footer-button",
            "button:has-text('See more')",
            "button:has-text('Ler mais')",
            "button:has-text('Ver mais')",
            "button:has-text('…more')",
            "button[aria-label*='more']",
        ]
        for sm_sel in see_more_selectors:
            try:
                sm_btn = page.locator(sm_sel)
                if await sm_btn.count() > 0 and await sm_btn.first.is_visible():
                    await sm_btn.first.click()
                    print(f"[EasyApply] Clicked 'See more' button ({sm_sel})")
                    await random_sleep(1.0, 2.0)
                    break
            except Exception:
                pass
        
        desc_text = ""
        desc_locators = [
            ".jobs-description-content__text",
            "#job-details",
            ".job-details-module",
            ".jobs-box__html-content",
            "article.jobs-description__container",
        ]
        
        for selector in desc_locators:
            try:
                loc = page.locator(selector)
                if await loc.count() > 0:
                    text = await loc.first.inner_text()
                    if text and len(text.strip()) > 50:
                        desc_text = text[:4000]
                        print(f"[EasyApply] Description found via '{selector}' ({len(desc_text)} chars)")
                        break
            except Exception:
                pass
        
        # If still no desc, try heading parent
        if not desc_text:
            try:
                heading = page.locator("h2:has-text('About the job'), h2:has-text('Sobre a vaga')")
                if await heading.count() > 0:
                    parent = heading.first.locator("..")
                    text = await parent.inner_text()
                    if text and len(text.strip()) > 50:
                        desc_text = text[:4000]
                        print(f"[EasyApply] Description found via heading parent ({len(desc_text)} chars)")
            except Exception:
                pass

        # STEP 3: Combine title + description. Title comes first for reliable language detection.
        parts = []
        if title_text:
            parts.append(title_text)
        if desc_text:
            parts.append(desc_text)
        job_description = "\n".join(parts)

    except Exception as e:
        print(f"[EasyApply] Soft exception during job description extraction: {e}")

    if job_description:
        print(f"[EasyApply] Language context extracted ({len(job_description)} chars). First 200: {job_description[:200]}")
    else:
        print(f"[EasyApply] WARNING: Job Description AND Title are EMPTY. Resume/language detection will default to PT.")

    try:
        locators = [
            page.locator("[data-view-name='job-apply-button']"),
            page.locator("button.jobs-apply-button"),
            page.locator("button.jobs-apply-button--disabled"),
            page.locator("button[aria-label*='Easy Apply']"),
            page.locator("button[aria-label*='Candidatura simplificada']"),
            page.locator("button:has-text('Easy Apply')"),
            page.locator("button:has-text('Candidatura simplificada')"),
            page.locator("a[href*='/apply/']")
        ]
        
        button = None
        for loc in locators:
            if await loc.count() > 0:
                for i in range(await loc.count()):
                    el = loc.nth(i)
                    if await el.is_visible():
                        button = el
                        break
            if button:
                break
                
        if not button:
            print(f"[EasyApply] Failed to locate Easy Apply button in Chromium DOM (SPA rendering freeze or really no button).")
            return False
            
        await random_sleep(1.0, 3.0)
        await button.click()
        await random_sleep(2.0, 4.0)

    except Exception as e:
        print(f"[EasyApply] Error clicking apply button: {e}")
        return False
    
    return await handle_form_loop(page, job_title=title_text, job_description=job_description)

async def handle_form_loop(page: Page, job_title: str = "", job_description: str = "") -> bool:
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
            print("[EasyApply] Final Submit screen reached. Submitting application...")
            await submit_btn.click()
            await random_sleep(3.0, 5.0)
            
            # Check if submission was successful (modal should close or show confirmation)
            try:
                # Wait a moment for any post-submit modal/confirmation
                await random_sleep(2.0, 3.0)
                # If the modal is still open, try to close it (could be a "Application submitted" confirmation)
                await close_modal(page)
            except Exception:
                pass
            
            print("[EasyApply] Application submitted successfully!")
            return True

        # If not submit, we must answer questions and click "Next" or "Review"
        
        # 0. Handle resume selection deterministically (bypasses AI)
        await handle_resume_selection(page, job_title, job_description)
        
        # 1. Extract fields (resume is NOT included, it's handled above)
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
    for fs_idx, fs in enumerate(fieldsets):
        try:
            if not await fs.is_visible():
                continue
                
            legend_loc = fs.locator("legend")
            legend = await legend_loc.inner_text() if await legend_loc.count() > 0 else "Radio Group"
            legend = legend.strip()
            
            radio_inputs = await fs.locator("input[type='radio']").all()
            if not radio_inputs:
                continue
            
            # Get a unique fieldset ID if available, otherwise use nth-of-type index
            fs_id = await fs.get_attribute("id")
            if fs_id:
                fs_selector = f"[id='{fs_id}']"
            else:
                fs_selector = f"fieldset >> nth={fs_idx}"
                
            opts = []
            for r_in in radio_inputs:
                r_id = await r_in.get_attribute("id")
                r_lbl_loc = modal.locator(f"label[for='{r_id}']")
                if await r_lbl_loc.count() > 0:
                    r_lbl = await r_lbl_loc.inner_text()
                else:
                    r_lbl = await fs.locator(f"[for='{r_id}']").inner_text() if await fs.locator(f"[for='{r_id}']").count() > 0 else r_id
                opts.append({"selector": f"[id='{r_id}']", "label": r_lbl.strip()})
                
            fields.append({"selector": fs_selector, "label": legend, "type": "radio", "options": opts})
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
            
    # 4. Resume Selection Container — handled deterministically by handle_resume_selection(), NOT by AI

    return fields

async def execute_ai_actions(page: Page, actions: list):
    """Executes the Playwright actions determined by the GPT model."""
    for action in actions:
        selector = action.get("selector")
        act_type = action.get("action")
        val = action.get("value")
        
        if not selector or act_type == "skip": continue
        
        # If the AI returns the fake 'resume_radios' but puts the real target in 'val' to satisfy JSON form rules
        if selector == "resume_radios" and act_type == "click" and val:
            if str(val).startswith("[id="):
                selector = str(val)

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
