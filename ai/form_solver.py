import json
from openai import AsyncOpenAI
from core.config import OPENAI_API_KEY, USER_PROFILE

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """You are an automated assistant helping a user apply for jobs on LinkedIn.
You will be provided with the user's profile information (in YAML format) and a list of form fields extracted from a job application modal.

Your goal is to determine the correct action and value to fill in each form field based *strictly* on the user's profile.

Profile Data:
{profile_data}

Critical Instructions:
1. Language Adaptation: Pay close attention to the language of the form fields (e.g., Portuguese or English). YOU MUST provide the `value` in the EXACT SAME language as the form question.
2. Handling Unknown Technologies/Skills: If a question asks for years of experience with a specific technology not listed in the profile (e.g., "Kubernetes", "C#"), DO NOT fail or leave it blank if an integer is required. Assume 1 year of experience (or "1") to bypass the ATS filter, unless asked if you have experience, then say "Sim, possuo conhecimentos fundamentais" or "Yes, I have foundational knowledge".
3. Personal/Subjective Questions: If asked "Why do you want to work here?" or similar, generate a polite, professional, and generic response highlighting the user's background in Java/Backend and eagerness to contribute, in the language of the question.
4. For text/number inputs (e.g., "Years of experience with Java"), provide the integer or text value required. If the question asks for years of experience generally, base it on the overall experience (3 years).
5. For radio buttons / selects (e.g., "Are you legally authorized to work in the US?"), choose the option that matches the profile or common sense if not explicitly stated (e.g., Yes to authorization if applying in their home country, "Brazilian" for citizenship, etc.).
6. Resume Selection: If you see options to select a resume (often radio buttons with file names), determine the language of the job application form. If the form is in Portuguese, select the option that appears to be the Portuguese resume (e.g., 'Curriculo', 'PT'). If the form is in English, select the option for the English resume (e.g., 'Resume', 'EN').
7. Always respond in valid JSON format ONLY.

Expected JSON Output Format:
[
  {{"selector": "input#id-123", "action": "type", "value": "3"}},
  {{"selector": "select#id-456", "action": "select", "value": "Yes"}},
  {{"selector": "input#radio-789", "action": "click", "value": null}}
]
"""

async def solve_form(fields_data: list) -> list:
    """
    Sends the extracted form fields to GPT-4o-mini and returns the list of actions to take.
    fields_data expected format: 
    [{"selector": "...", "label": "How many years of experience?", "type": "input", "options": []}]
    """
    if not OPENAI_API_KEY:
        print("[AI] WARNING: OPENAI_API_KEY is not set. Cannot solve form.")
        return []

    # Prepare context
    import yaml
    profile_str = yaml.dump(USER_PROFILE)
    
    prompt = SYSTEM_PROMPT.format(profile_data=profile_str)
    
    user_content = "Please provide the actions for the following form fields:\n" + json.dumps(fields_data, indent=2)

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"} if False else None, # Enforcing via prompt is generally safe with mini + good prompt, but we can wrap. Let's rely on standard parsing first
            temperature=0.0
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Clean up possible markdown code block wrappers
        if result_text.startswith("```json"):
            result_text = result_text[7:-3].strip()
        elif result_text.startswith("```"):
            result_text = result_text[3:-3].strip()

        actions = json.loads(result_text)
        return actions if isinstance(actions, list) else []

    except Exception as e:
        print(f"[AI] Error solving form with GPT: {e}")
        return []
