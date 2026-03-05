import json
from openai import AsyncOpenAI
from core.config import OPENAI_API_KEY, USER_PROFILE

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """You are an automated assistant helping a user apply for jobs on LinkedIn.
You will be provided with the user's profile information (in YAML format), the Job Description, and a list of form fields extracted from a job application modal.

Your goal is to determine the correct action and value to fill in each form field based *strictly* on the user's profile.

Profile Data:
{profile_data}

Job Description:
{job_description}


Critical Instructions:
1. Language Adaptation: Pay close attention to the language of the Job Description. YOU MUST provide the `value` for subjective/text questions in the EXACT SAME language as the Job Description, disregarding the language of the form fields (which might be automatically translated by the UI).
2. Handling KNOWN Technologies: If a question asks about your experience with a technology explicitly listed in your profile (e.g., "Spring Boot", "Java", "Docker"), and requires a text response, assert your expertise confidently and specify your years of experience (e.g., "I have 3 years of professional experience building microservices with Spring Boot"). If it requires a number, provide the exact years from the profile (e.g., "3").
3. Handling UNKNOWN Technologies: If a question asks for experience with a technology NOT listed in the profile (e.g., "Kubernetes", "C#"), DO NOT fail or leave it blank if an integer is required. Assume 1 year of experience (or "1") to bypass the ATS filter. If a text response is required, say "Sim, possuo conhecimentos fundamentais" or "Yes, I have foundational knowledge".
4. Salary/Compensation Expectations: If a question asks for salary expectations (and the input requires a number), you MUST provide ONLY digits (e.g., "10000"). DO NOT include text like "Negociável", "Negotiable", currency symbols like "R$" or "$", or punctuation. To determine the number: 
   - First, check the Job Description to see if a salary range or budget is explicitly stated; if so, pick a number near the middle of that range. 
   - If no salary is stated, infer the seniority of the role (Junior, Pleno/Mid-level, or Senior).
   - Then, infer the currency based on the Job Description location or language (e.g., jobs in Brazil or in Portuguese use BRL; US, Europe, or International Remote jobs use USD). 
   - Pick the corresponding numeric value from the profile's `salary_expectation` under the inferred currency (BRL or USD) and seniority (junior, pleno, or senior).
5. Personal/Subjective Questions: If asked "Why do you want to work here?" or similar, generate a polite, professional, and generic response highlighting the user's background in Java/Backend and eagerness to contribute, in the language of the question.
6. Current Company: If asked for your current employer or company, provide the exact `current_company` value from the profile (e.g., "Velsis").
7. For text/number inputs: If a question asks for years of experience generally (not a specific tech), base it on the overall experience (3 years).
8. For radio buttons / selects (e.g., "Are you legally authorized to work in the US?"), choose the option that matches the profile or common sense if not explicitly stated (e.g., Yes to authorization if applying in their home country, "Brazilian" for citizenship, etc.). CRITICAL: For radio button lists, you MUST provide the specific `selector` of the chosen option from the `options` array, NOT the 'fieldset' or group selector.
9. Checkboxes/Consent: If you see a checkbox asking for consent, agreement to terms, policy acknowledgment, or stating "I agree" etc., you MUST check it by returning "action": "click" for that selector.
10. Resume Selection: If you see options to select a resume, determine the language of the Job Description (ignore form UI language). If the Job Description is in Portuguese, you MUST select the exact option that contains "Curriculo.pdf". If the Job Description is in English, you MUST select the exact option that contains "Resume.pdf".
11. Docs/IDs: If asked for CPF or RG (identity document), use the exact values from the profile.
12. Date of Birth/Age: If asked for Date of Birth, provide the exact `birth_date` from the profile (e.g., "21/09/2001"), formatting it as the form requires (MM/DD/YYYY or DD/MM/YYYY).
13. Phone number: Always include the area code (e.g., "41").
14. Answer ALL fields: You must provide exactly one action for EVERY field object provided in the input JSON. Do not skip any fields (like radio buttons or text areas) even if they ask about the same topic (like disability).
15. Always respond in valid JSON format ONLY. CRITICAL: Return the exact `selector` string provided in the input JSON without modifying or converting it.

Expected JSON Output Format:
[
  {{"selector": "[id='id-123']", "action": "type", "value": "3"}},
  {{"selector": "[id='id-456']", "action": "select", "value": "Yes"}},
  {{"selector": "[id='radio-789']", "action": "click", "value": null}}
]
"""

async def solve_form(fields_data: list, job_description: str = "") -> list:
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
    
    prompt = SYSTEM_PROMPT.format(profile_data=profile_str, job_description=job_description)
    
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
