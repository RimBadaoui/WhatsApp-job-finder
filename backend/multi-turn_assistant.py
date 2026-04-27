from llmproxy import LLMProxy
from wa_service_sdk import BaseEvent, TextEvent, InteractiveEvent, AudioEvent, create_message, create_buttoned_message, create_list_message, download_media, media_uri_from_event
import json
import re
import requests

# ----------------------------
# LLM setup
# ----------------------------
client = LLMProxy()

MODEL_NAME = "gemini-2.5-flash-lite"
TEMPERATURE = 0.0
LAST_K = 10

# ----------------------------
# Messages
# ----------------------------
INTRO_MESSAGE = """Hi! 👋 I'm an employment support assistant for immigrants in Greater Boston.

I can help you find:
- Job opportunities and resources
- Workforce training programs
- Resume help
- Local organizations that support employment

I only help with employment-related questions. For legal advice about visas or immigration status, please contact a qualified attorney.

What can I help you with today?"""

OUT_OF_SCOPE_RESPONSE = "I'm only able to help with employment and job-related questions. For anything else, I'd recommend reaching out to a relevant local organization. Is there anything job-related I can help you with?"

LEGAL_RESPONSE = (
    "I can share general employment resources, but I can't give legal advice about "
    "immigration status, visas, or work authorization. For trusted help, please contact "
    "a qualified immigration attorney or a local organization such as the "
    "International Institute of New England. Is there anything employment-related I can help you with?"
)

# ----------------------------
# Per-user state
# ----------------------------
user_sessions = {}

def new_profile():
    return {
        "name": None,
        "preferred_language": None,
        "location": None,
        "employment_goal": None,
        "job_interests": [],
        "work_experience": None,
        "english_level": None,
        "transportation_access": None,
        "needs_nearby_work": False,
        "needs_remote_work": False,
        "needs_training": None,
        "needs_worker_rights_help": False,
        "availability": None,
        "has_resume": None,
        "open_questions": []
    }

def get_session(user_id):
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "profiles": [new_profile()],
            "active_profile_index": 0,
            "conversation_history": [],
            "profile_history_start": [0],  # index into conversation_history where each profile started
            "greeted": False,
            "onboarding_step": "done",
            "awaiting_profile_clarification": False,
            "recommendation_sent": False,
        }
    return user_sessions[user_id]

def active_profile(session):
    return session["profiles"][session["active_profile_index"]]

# ----------------------------
# Interactive field map
# ----------------------------
INTERACTIVE_FIELD_MAP = {
    "lang_english": ("preferred_language", "English"),
    "lang_arabic": ("preferred_language", "Arabic"),
    "english_beginner": ("english_level", "beginner"),
    "english_intermediate": ("english_level", "intermediate"),
    "english_advanced": ("english_level", "advanced"),
    "transport_car": ("transportation_access", "has car"),
    "transport_transit": ("transportation_access", "public transit only"),
    "transport_limited": ("transportation_access", "limited transportation"),
    "availability_fulltime": ("availability", "full-time"),
    "availability_parttime": ("availability", "part-time"),
    "availability_either": ("availability", "either"),
    "resume_yes": ("has_resume", "yes"),
    "resume_no": ("has_resume", "no"),
    "training_yes": ("needs_training", True),
    "training_no": ("needs_training", False),
}

# ----------------------------
# Prompts
# ----------------------------
SCOPE_CLASSIFIER_PROMPT = '''
You are a guardrail for an employment support chatbot.

Classify the user message into one of these categories:
- "employment": the message is about jobs, work, training, resume, career, workforce, employment resources, or related topics
- "legal": the message is about visas, green cards, asylum, undocumented status, work authorization, immigration papers
- "other": the message is clearly unrelated to employment (e.g. weather, sports, personal relationships, health, etc.)

Return only one word: employment, legal, or other.
'''

THIRD_PARTY_CLASSIFIER_PROMPT = '''
You are a guardrail for an employment support chatbot.

Determine if the user's message is asking about someone else (a friend, family member, spouse, etc.) rather than themselves.

Examples of third-party messages:
- "My friend needs a job"
- "Can you help my sister find work?"
- "My husband is looking for training programs"

Examples of self-messages:
- "I need a job"
- "I'm looking for work in Boston"
- "Do you have resume help?"

Return only one word: self or other.
'''

PROFILE_BUILDER_PROMPT = '''
You are a profile builder for a multilingual employment-resource chatbot that supports immigrants in Greater Boston.

Update the user's structured employment profile based on the full conversation history and the latest user message.

Only extract information the user explicitly states or clearly implies. Do not guess.
Preserve existing values unless the user provides new conflicting information.
Return only valid JSON.

Rules:
- If the user says "no" to work_experience, set work_experience to "no prior work experience".
- If the user says "yes" to needs_training, set needs_training to true.
- If the user says "no" to needs_training, set needs_training to false.
- If the user says "yes" to has_resume, set has_resume to "yes".
- If the user says "no" to has_resume, set has_resume to "no".
- If the user mentions their name, set name to that value.
- Keep open_questions as an empty list.

Normalization:
- preferred_language: only "English" or "Arabic"
- location: "Boston", "Chelsea", "East Boston", "Somerville", "Greater Boston", etc.
- employment_goal: "find a job", "find job training", "resume help", etc.
- job_interests: list of job types or industries
- work_experience: short summary like "retail experience", "no prior work experience"
- english_level: "beginner", "intermediate", or "advanced"
- transportation_access: "has car", "public transit only", "limited transportation", "no transportation"
- availability: "full-time", "part-time", or "either"
- has_resume: "yes", "no", or "needs help making one"
- name: first name or full name if provided

Return the full updated JSON object and nothing else.

Schema:
{
  "name": null,
  "preferred_language": null,
  "location": null,
  "employment_goal": null,
  "job_interests": [],
  "work_experience": null,
  "english_level": null,
  "transportation_access": null,
  "needs_nearby_work": false,
  "needs_remote_work": false,
  "needs_training": null,
  "needs_worker_rights_help": false,
  "availability": null,
  "has_resume": null,
  "open_questions": []
}
'''

FOLLOWUP_PROMPT = '''
You are a warm, knowledgeable employment support assistant helping immigrants in Greater Boston.

The user has already received job resource recommendations. They are now asking a follow-up question.

Your job:
- Answer their specific follow-up question helpfully and concisely.
- If they ask what happens after filling out a form or contacting an org, explain the general process warmly.
- If they ask about a specific organization from the recommendations, give helpful context and include its URL.
- If they ask about a resource not in the original recommendations, use web search to find it and include its verified URL.
- If you recommend ANY organization, you MUST include its URL in parentheses. If you cannot find a confirmed URL via web search, do not mention that organization.
- Never list organizations without URLs — an org name with no link is not helpful and may be fabricated.
- If they ask something outside employment support, politely redirect.
- Keep your response short — 2-4 sentences max.
- Do not repeat the full recommendations list unless explicitly asked.

Return only the response text.
'''

POST_RECOMMENDATION_CLASSIFIER_PROMPT = '''
You are a router for an employment support chatbot.

The user has already received job resource recommendations. Classify their new message into one of these categories:

- "followup": the message is a natural continuation of the recommendations — asking what happens next, asking about a recommended org, asking for more details, asking career/certification questions related to their job interest, or any question that can be answered conversationally without starting a new search.
- "new_profile": the user is explicitly starting a NEW job search for a DIFFERENT person or a completely different career goal (e.g. "my husband also needs a job", "can you help my sister find work", "actually I want to look for construction jobs instead")
- "employment": a broad new employment question not tied to their specific situation (e.g. "what is a cover letter?", "how does unemployment work?")
- "legal": the message is about visas, green cards, asylum, undocumented status, work authorization, immigration papers
- "other": clearly unrelated to employment (e.g. weather, sports, personal relationships, health)

Examples:
- "He filled out the form, what happens now?" → followup (acting on existing recommendation)
- "She applied, what should she do next?" → followup (acting on existing recommendation)
- "Do I need certification to work as a nurse?" → followup (career question about their job interest)
- "What about HireCulture?" → followup (asking about a specific resource)
- "Can I do this part time?" → followup
- "My husband also needs a job" → new_profile (new job search for different person)
- "Actually I want construction jobs" → new_profile (completely different goal)
- "My sister needs help finding work" → new_profile

When in doubt, classify as "followup" — it is always safer to answer conversationally than to restart the intake flow.

Return only one word: followup, new_profile, employment, legal, or other.
'''

NEXT_QUESTION_PROMPT = '''
You are a warm, conversational employment support assistant helping immigrants in Greater Boston.

You are in the middle of an intake conversation. Your job is to:
1. First, briefly acknowledge or react to what the user just said (1 sentence max — warm and natural, not generic).
2. Then ask ONE question about the FIRST missing field listed below.

Missing fields still needed (ask about the FIRST one only):
{missing_fields}

Rules:
- ALWAYS start with a brief, specific acknowledgment of the user's last message before asking the next question.
- Ask ONLY about the first field in the list above. Do not ask about any other topic.
- NEVER ask about availability, full-time vs part-time, transportation, resume, or training — those are handled separately with buttons.
- Build on what the user already said when possible — reference their specific words.
- Do not repeat questions already answered.
- Do not ask about sensitive legal or immigration status.
- Keep it short and friendly — 2-3 sentences total.

Return only the response text, nothing else.
'''

RECOMMENDATION_PROMPT = '''
You are an AI assistant helping immigrants in Greater Boston find employment resources, job opportunities, and workforce training programs.

CRITICAL — follow this exact process before writing your response:
1. Use web search to find real organizations in Greater Boston that match this user's profile. Search specifically for their job interest first (e.g. "artist jobs Boston immigrants", "nursing training Boston", "construction jobs Cambridge"). Prioritize organizations that are SPECIFIC to their field over general job boards. Only include general resources like MassHire or job boards if you cannot find enough field-specific ones.
2. For each organization found, do a second web search to confirm its exact homepage URL. Only use the URL that appears directly in search results — never construct or guess a URL.
3. Find at least 4-5 confirmed organizations so that even if some are removed during verification, the user still receives at least 2-3 solid recommendations.

Rules:
1. DO NOT provide legal advice about immigration, visas, asylum, green cards, or work authorization.
2. DO NOT make up information. Only recommend organizations confirmed by your search results.
3. DO NOT ask for sensitive personal information.
4. Keep responses simple, clear, supportive, and easy to understand.
5. Stay focused on employment support only.
6. Do not guarantee outcomes or make promises.
7. Every resource with a URL MUST include its full website URL in parentheses. If you cannot confirm a URL, you may still mention the organization by name without a link rather than omitting it entirely.

Personalization rules — apply ALL of these:
- If the user has a name, address them by name in the opening line.
- Mention their specific job interest by name — never say "your field" generically.
- If they want training, recommend training programs specifically for their job interest.
- If they have limited English, prioritize bilingual or multilingual programs.
- If they have limited transportation, only recommend transit-accessible or remote options.
- If they need a resume, include a resume help resource.
- If they are looking for part-time work, filter accordingly.
- Mention their location when referencing nearby resources.

Your response MUST follow this structure:

1. One warm, personalized opening sentence using their name and specific situation.

2. RESOURCES — 2-4 organizations relevant to their job interest and location, formatted as:
   *Resource Name* (https://url-here.org): One sentence on why it fits this person.
   If no URL is available for an org, format as:
   *Resource Name*: One sentence on why it fits this person.

3. TIPS FOR [THEIR SPECIFIC JOB INTEREST] — 3-4 bullet points of practical field-specific advice that does not require links, such as:
   - Where job postings for this field are typically found
   - Certifications or skills that help in this specific field
   - How immigrants typically break into this field in the Boston area
   - Relevant local networks, unions, or communities for this field

4. NEXT STEPS — 2-3 concrete actions tailored to their profile.

5. One encouraging closing line.

Do not output JSON.
'''

VERIFIER_PROMPT = """
You are a fact-checker for an employment resource chatbot.

You will receive a draft response recommending organizations and resources to a job-seeker.

Your job:
1. For each organization or resource mentioned with a URL, check if the URL is valid and complete.
2. If a resource has a malformed or obviously fake URL (e.g. "https://example.com", placeholder text), remove that URL but keep the organization name.
3. Do not add, invent, or look up any new organizations or URLs.
4. Do not add any new text, lines, or resources that were not in the original response.
5. Do not change any other part of the response — keep the tone, structure, and personalization intact.
6. Organizations listed without URLs are allowed — do not remove them.

Return the corrected response text only. No explanations.
"""

DYNAMIC_OPTIONS_PROMPT = '''
You are generating quick-reply buttons for a WhatsApp chatbot helping immigrants find jobs in Greater Boston.

Given a question the bot just asked, generate exactly 2 specific, meaningful answer options + "Other" as the third button.

Rules:
- Always generate 3 options total: 2 specific answers + {"id": "other_freetext", "title": "Other"}
- Each option title must be 20 characters or fewer
- Each option must have a unique short id (snake_case)
- Options must be SPECIFIC and USEFUL — not meta-categories like "Specific job" or "Job field"
- For job type questions: give 2 common job categories (e.g. "Healthcare", "Construction")
- For location questions: give 2 specific Greater Boston neighborhoods/areas (e.g. "East Boston", "Cambridge")
- For experience questions: give 2 realistic experience levels (e.g. "Some experience", "No experience")
- Only skip buttons if the question is truly personal and unique (e.g. "What is your name?")

Examples:
- "What kind of work are you looking for?" → ["Healthcare", "Construction", "Other"]
- "Where in Greater Boston?" → ["East Boston", "Cambridge", "Other"]
- "Tell me about your work experience" → ["Some experience", "No experience", "Other"]
- "What is your name?" → use_buttons: false

Return only valid JSON:
{
  "use_buttons": true,
  "question_text": "the question to display",
  "options": [
    {"id": "option_id", "title": "Short Label"},
    {"id": "option_id2", "title": "Short Label 2"},
    {"id": "other_freetext", "title": "Other"}
  ]
}

Or if free text is the only option:
{
  "use_buttons": false,
  "question_text": "the question to display",
  "options": []
}
'''

# ----------------------------
# Profile helpers
# ----------------------------
def get_missing_fields(profile_dict):
    missing = []
    if not profile_dict.get("job_interests"):
        missing.append("job interests (what kind of work they're looking for)")
    if not profile_dict.get("location"):
        missing.append("location (what area they live in or want to work in)")
    if profile_dict.get("work_experience") is None:
        missing.append("past work experience")
    if profile_dict.get("transportation_access") is None:
        missing.append("transportation access (car, public transit, limited)")
    if profile_dict.get("availability") is None:
        missing.append("availability (full-time, part-time, either)")
    if profile_dict.get("has_resume") is None:
        missing.append("whether they have a resume or need help making one")
    if profile_dict.get("needs_training") is None:
        missing.append("whether they want job training or skill-building")
    return missing

BUTTON_HANDLED_FIELDS = {
    "transportation access (car, public transit, limited)",
    "availability (full-time, part-time, either)",
    "whether they have a resume or need help making one",
    "whether they want job training or skill-building",
}

def get_llm_askable_fields(profile_dict):
    return [f for f in get_missing_fields(profile_dict) if f not in BUTTON_HANDLED_FIELDS]

def enough_info(profile_dict):
    return len(get_missing_fields(profile_dict)) == 0

def build_profile_summary(profile_dict):
    return (
        f"Name: {profile_dict.get('name') or 'Unknown'}\n"
        f"Preferred language: {profile_dict.get('preferred_language') or 'Unknown'}\n"
        f"English level: {profile_dict.get('english_level') or 'Unknown'}\n"
        f"Location: {profile_dict.get('location') or 'Unknown'}\n"
        f"Employment goal: {profile_dict.get('employment_goal') or 'Unknown'}\n"
        f"Job interests: {', '.join(profile_dict['job_interests']) if profile_dict.get('job_interests') else 'Unknown'}\n"
        f"Work experience: {profile_dict.get('work_experience') or 'Unknown'}\n"
        f"Transportation access: {profile_dict.get('transportation_access') or 'Unknown'}\n"
        f"Needs nearby work: {profile_dict.get('needs_nearby_work', False)}\n"
        f"Needs remote work: {profile_dict.get('needs_remote_work', False)}\n"
        f"Needs training: {profile_dict.get('needs_training')}\n"
        f"Needs worker rights help: {profile_dict.get('needs_worker_rights_help', False)}\n"
        f"Availability: {profile_dict.get('availability') or 'Unknown'}\n"
        f"Has resume: {profile_dict.get('has_resume') or 'Unknown'}"
    )

def format_conversation_history(history):
    return "\n".join(f"{t['role'].capitalize()}: {t['text']}" for t in history)

# ----------------------------
# Helpers
# ----------------------------
def _is_dead_url(url: str) -> bool:
    import socket
    from urllib.parse import urlparse
    try:
        hostname = urlparse(url).hostname
        if hostname:
            socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return True
    try:
        resp = requests.get(url, allow_redirects=True, timeout=8,
                            headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code >= 400:
            return True
        return False
    except requests.RequestException:
        return False

def remove_dead_links(text: str) -> str:
    urls = re.findall(r'https?://[^\s\)\]"\']+', text)
    for url in set(urls):
        if _is_dead_url(url):
            text = text.replace(url, "")
    text = re.sub(r'\(\s*\)', '', text)
    return text.strip()

def verify_recommendations(rec_text: str) -> str:
    result = client.generate(
        model=MODEL_NAME,
        system=VERIFIER_PROMPT,
        query=rec_text,
        temperature=0.0,
        lastk=1,
        session_id="verifier",
        rag_usage=False,
        websearch=False
    )
    return result["result"].strip()

def safe_json_load(text: str):
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        inner = lines[1:] if lines[0].startswith("```") else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        stripped = "\n".join(inner)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None

def merge_profile(current_profile, new_profile_data):
    merged = current_profile.copy()
    for key, value in new_profile_data.items():
        if key not in merged:
            continue
        if value is None:
            continue
        merged[key] = value
    return merged

# ----------------------------
# Dynamic button generation
# ----------------------------
def generate_dynamic_buttons(question_text: str, user_id: str):
    result = client.generate(
        model=MODEL_NAME,
        system=DYNAMIC_OPTIONS_PROMPT,
        query=f"Question: {question_text}",
        temperature=0.0,
        lastk=1,
        session_id=f"{user_id}_buttons",
        rag_usage=False,
        websearch=False
    )
    parsed = safe_json_load(result.get("result", ""))
    if not parsed:
        return None
    return parsed

def send_question_with_dynamic_buttons(user_id: str, question_text: str, session: dict):
    parsed = generate_dynamic_buttons(question_text, user_id)
    if parsed and parsed.get("use_buttons") and parsed.get("options"):
        options = parsed["options"]
        display_text = parsed.get("question_text", question_text)
        if "dynamic_button_map" not in session:
            session["dynamic_button_map"] = {}
        for opt in options:
            session["dynamic_button_map"][opt["id"]] = opt["title"]
        if len(options) <= 3:
            return create_buttoned_message(
                user_id=user_id,
                text=display_text,
                buttons=[{"id": o["id"], "title": o["title"]} for o in options]
            )
        else:
            return create_list_message(
                user_id=user_id,
                text=display_text,
                button_text="Select an option",
                rows=[{"id": o["id"], "title": o["title"]} for o in options]
            )
    return create_message(user_id=user_id, text=question_text)

# ----------------------------
# Classifiers
# ----------------------------
def classify_post_recommendation(user_message: str, user_id: str, session: dict) -> str:
    history_str = format_conversation_history(session["conversation_history"][-6:])
    result = client.generate(
        model=MODEL_NAME,
        system=POST_RECOMMENDATION_CLASSIFIER_PROMPT,
        query=(
            f"RECENT CONVERSATION:\n{history_str}\n\n"
            f"NEW USER MESSAGE: {user_message}"
        ),
        temperature=0.0,
        lastk=1,
        session_id=f"{user_id}_postroute",
        rag_usage=False,
        websearch=False
    )
    return result["result"].strip().lower()

def classify_scope(user_message: str, user_id: str, session: dict) -> str:
    if session.get("onboarding_step") == "done":
        missing = get_missing_fields(active_profile(session))
        if missing:
            return "employment"
    result = client.generate(
        model=MODEL_NAME,
        system=SCOPE_CLASSIFIER_PROMPT,
        query=user_message,
        temperature=0.0,
        lastk=1,
        session_id=f"{user_id}_scope",
        rag_usage=False,
        websearch=True
    )
    return result["result"].strip().lower()

def classify_third_party(user_message: str, user_id: str) -> str:
    result = client.generate(
        model=MODEL_NAME,
        system=THIRD_PARTY_CLASSIFIER_PROMPT,
        query=user_message,
        temperature=0.0,
        lastk=1,
        session_id=f"{user_id}_thirdparty",
        rag_usage=False,
        websearch=True
    )
    return result["result"].strip().lower()

def build_recommendation_with_rag(profile_dict, user_id):
    profile_summary = build_profile_summary(profile_dict)
    print("[DEBUG] Building recommendation for profile:", json.dumps(profile_dict, indent=2, ensure_ascii=False))
    if not profile_dict.get("job_interests"):
        print("[DEBUG] WARNING: job_interests is empty — recommendation will be generic")
    recommendation = client.generate(
        model=MODEL_NAME,
        system=RECOMMENDATION_PROMPT,
        query=(
            "STEP 1: Use web search to find real organizations in Greater Boston that match this user's profile. "
            "Search specifically for their job interest first (e.g. 'artist jobs Boston immigrants', 'nursing training Boston', 'construction jobs Cambridge'). "
            "Prioritize organizations that are SPECIFIC to their field over general job boards. "
            "Only include general resources like MassHire or job boards if you cannot find enough field-specific ones.\n\n"
            "STEP 2: For each organization found, do a second web search to confirm its exact homepage URL. "
            "Only use the URL that appears directly in search results — never construct or guess a URL.\n\n"
            "STEP 3: Write the personalized recommendation using ONLY organizations confirmed in STEP 1 and STEP 2. "
            "Field-specific organizations must appear BEFORE general job boards in the response. "
            "Do not include any organization you did not find in this session.\n\n"
            f"USER PROFILE:\n{profile_summary}\n\n"
            "You MUST reference their specific job interest, location, availability, English level, "
            "transportation access, resume status, and training needs in your response. "
            "Do not write a generic response — every recommendation must explain why it fits this specific person.\n"
            "IMPORTANT: Find at least 4-5 organizations so that even if some are removed during verification, "
            "the user still receives at least 2-3 solid recommendations. "
            "Every resource must include its exact URL from your search results or retrieved documents. "
            "Do not modify, guess, or construct URLs. If you cannot confirm a URL, still include the organization name without a URL.\n"
        ),
        temperature=TEMPERATURE,
        lastk=LAST_K,
        session_id="rag",
        rag_usage=True,
        websearch=True
    )

    print("[DEBUG] Full RAG response keys:", recommendation.keys())
    print("[DEBUG] Full RAG response:", json.dumps(recommendation, indent=2, ensure_ascii=False))
    print("[DEBUG] RAG context length:", len(recommendation.get("rag_context", "")))
    print("[DEBUG] RAG context preview:", recommendation.get("rag_context", "")[:300])

    raw_result = recommendation.get("result", "").strip()
    print("[DEBUG] Raw result before link check:", raw_result[:500])

    if not raw_result:
        print("[DEBUG] RAG returned empty result — falling back to web search only")
        fallback = client.generate(
            model=MODEL_NAME,
            system=RECOMMENDATION_PROMPT,
            query=(
                f"Find real employment resources in Greater Boston for this person and write a personalized recommendation.\n\n"
                f"USER PROFILE:\n{profile_summary}\n\n"
                "Search the web for organizations matching their job interest and location. "
                "Only include organizations with confirmed URLs from your search results."
            ),
            temperature=TEMPERATURE,
            lastk=LAST_K,
            session_id=f"{user_id}_fallback",
            rag_usage=False,
            websearch=True
        )
        print("[DEBUG] Fallback response:", json.dumps(fallback, indent=2, ensure_ascii=False))
        raw_result = fallback.get("result", "").strip()

    if not raw_result:
        print("[DEBUG] Fallback also returned empty — returning default message")
        return (
            "I'm sorry, I wasn't able to find specific resources right now. "
            "Please try reaching out to MassHire Greater Boston at https://masshireboston.org/ — "
            "they can help connect you with job opportunities and training programs in your area."
        )

    result = remove_dead_links(raw_result)
    print("[DEBUG] After remove_dead_links:", result[:500])
    result = verify_recommendations(result)
    print("[DEBUG] After verify_recommendations:", result[:500])
    return result

def get_next_question_from_llm(profile_dict, conversation_history, user_id):
    missing = get_llm_askable_fields(profile_dict)
    missing_str = "\n".join(f"- {f}" for f in missing)
    history_str = format_conversation_history(conversation_history)
    result = client.generate(
        model=MODEL_NAME,
        system=NEXT_QUESTION_PROMPT.format(missing_fields=missing_str),
        query=(
            f"CONVERSATION SO FAR:\n{history_str}\n\n"
            "What is the single best next question to ask?"
        ),
        temperature=0.3,
        lastk=LAST_K,
        session_id=f"{user_id}_questions",
        rag_usage=False,
        websearch=True
    )
    return result["result"].strip()

def update_profile_from_history(session, user_id):
    profile = active_profile(session)
    # Only use conversation history from when this profile started
    profile_start = session.get("profile_history_start", [0])[session["active_profile_index"]]
    relevant_history = session["conversation_history"][profile_start:]
    history_str = format_conversation_history(relevant_history)
    profile_builder = client.generate(
        model=MODEL_NAME,
        system=PROFILE_BUILDER_PROMPT,
        query=(
            f"CURRENT_PROFILE_JSON:\n{json.dumps(profile, ensure_ascii=False)}\n\n"
            f"CONVERSATION HISTORY:\n{history_str}\n\n"
            "Return only the full updated JSON object."
        ),
        temperature=TEMPERATURE,
        lastk=LAST_K,
        session_id=user_id,
        rag_usage=False,
        websearch=True
    )
    raw = profile_builder.get("result", "")
    print("[DEBUG] profile_builder raw result:", repr(raw))
    parsed = safe_json_load(raw)
    print("[DEBUG] profile_builder parsed:", parsed)
    if parsed is not None:
        session["profiles"][session["active_profile_index"]] = merge_profile(profile, parsed)

# ----------------------------
# Interactive UI helpers
# ----------------------------
def language_buttons(user_id):
    return create_buttoned_message(
        user_id=user_id,
        text="What language do you prefer? We support English and Arabic.",
        buttons=[
            {"id": "lang_english", "title": "English"},
            {"id": "lang_arabic", "title": "Arabic"},
        ]
    )

def english_level_list(user_id):
    return create_list_message(
        user_id=user_id,
        text="How comfortable are you with English at work?",
        button_text="Select level",
        rows=[
            {"id": "english_beginner", "title": "Beginner", "description": "Basic or limited English"},
            {"id": "english_intermediate", "title": "Intermediate", "description": "Conversational English"},
            {"id": "english_advanced", "title": "Advanced", "description": "Fluent or near-fluent"},
        ]
    )

def transportation_buttons(user_id):
    return create_buttoned_message(
        user_id=user_id,
        text="How do you usually get around?",
        buttons=[
            {"id": "transport_car", "title": "I have a car"},
            {"id": "transport_transit", "title": "Public transit"},
            {"id": "transport_limited", "title": "Limited transport"},
        ]
    )

def availability_buttons(user_id):
    return create_buttoned_message(
        user_id=user_id,
        text="Are you looking for full-time, part-time, or either?",
        buttons=[
            {"id": "availability_fulltime", "title": "Full-time"},
            {"id": "availability_parttime", "title": "Part-time"},
            {"id": "availability_either", "title": "Either"},
        ]
    )

def resume_buttons(user_id):
    return create_buttoned_message(
        user_id=user_id,
        text="Do you already have a resume?",
        buttons=[
            {"id": "resume_yes", "title": "Yes, I have one"},
            {"id": "resume_no", "title": "No, need help"},
        ]
    )

def training_buttons(user_id):
    return create_buttoned_message(
        user_id=user_id,
        text="Would job training or skill-building be useful for you?",
        buttons=[
            {"id": "training_yes", "title": "Yes"},
            {"id": "training_no", "title": "No"},
        ]
    )

# ----------------------------
# Ask next question (strict order)
# ----------------------------
async def _ask_next(session, user_id, profile):
    if profile.get("transportation_access") is None and profile.get("job_interests") and profile.get("location") and profile.get("work_experience") is not None:
        session["conversation_history"].append({"role": "assistant", "text": "[Sent transportation options]"})
        return create_buttoned_message(
            user_id=user_id,
            text="Great, thanks! I just need a bit more information before I can give you my best recommendations. How do you usually get around?",
            buttons=[
                {"id": "transport_car", "title": "I have a car"},
                {"id": "transport_transit", "title": "Public transit"},
                {"id": "transport_limited", "title": "Limited transport"},
            ]
        )

    if profile.get("availability") is None and profile.get("transportation_access") is not None:
        session["conversation_history"].append({"role": "assistant", "text": "[Sent availability options]"})
        return create_buttoned_message(
            user_id=user_id,
            text="Almost there! Are you looking for full-time, part-time, or either?",
            buttons=[
                {"id": "availability_fulltime", "title": "Full-time"},
                {"id": "availability_parttime", "title": "Part-time"},
                {"id": "availability_either", "title": "Either"},
            ]
        )

    if profile.get("has_resume") is None and profile.get("availability") is not None:
        session["conversation_history"].append({"role": "assistant", "text": "[Sent resume options]"})
        return create_buttoned_message(
            user_id=user_id,
            text="One more thing — do you already have a resume, or would you like help making one?",
            buttons=[
                {"id": "resume_yes", "title": "Yes, I have one"},
                {"id": "resume_no", "title": "No, need help"},
            ]
        )

    if profile.get("needs_training") is None and profile.get("has_resume") is not None:
        session["conversation_history"].append({"role": "assistant", "text": "[Sent training options]"})
        return create_buttoned_message(
            user_id=user_id,
            text="Last question! Would job training or skill-building be useful for you?",
            buttons=[
                {"id": "training_yes", "title": "Yes"},
                {"id": "training_no", "title": "No"},
            ]
        )

    q = get_next_question_from_llm(profile, session["conversation_history"], user_id)
    session["conversation_history"].append({"role": "assistant", "text": q})
    return send_question_with_dynamic_buttons(user_id, q, session)

# ----------------------------
# Main WhatsApp handler
# ----------------------------
async def handle_event(event: BaseEvent):

    # --- Interactive button/list responses ---
    if isinstance(event, InteractiveEvent):
        user_id = event.user_id
        session = get_session(user_id)

        interactive_id = getattr(event, "interaction_id", None)
        print(f"[DEBUG] Resolved interactive_id: {interactive_id}")

        if interactive_id == "profile_self":
            session["awaiting_profile_clarification"] = False
            session["recommendation_sent"] = False
            session["active_profile_index"] = 0
            session["conversation_history"].append({"role": "user", "text": "[Selected: For myself]"})
            profile = active_profile(session)
            if enough_info(profile):
                reply = "Of course! You're looking for nursing roles. Would you like me to search for more resources, or is there something specific I can help you with?"
                session["conversation_history"].append({"role": "assistant", "text": reply})
                return create_message(user_id=user_id, text=reply)
            return await _ask_next(session, user_id, profile)

        if interactive_id == "profile_other":
            session["awaiting_profile_clarification"] = False
            session["recommendation_sent"] = False
            session["profiles"].append(new_profile())
            session["active_profile_index"] = len(session["profiles"]) - 1
            # Mark where this new profile's history starts
            session["profile_history_start"].append(len(session["conversation_history"]))
            session["conversation_history"].append({"role": "user", "text": "[Selected: For someone else]"})
            update_profile_from_history(session, user_id)
            return await _ask_next(session, user_id, active_profile(session))

        if interactive_id and interactive_id in INTERACTIVE_FIELD_MAP:
            field, value = INTERACTIVE_FIELD_MAP[interactive_id]
            session["profiles"][session["active_profile_index"]][field] = value
            session["conversation_history"].append({"role": "user", "text": f"[Selected: {value}]"})
            profile = active_profile(session)

            if enough_info(profile):
                rec = build_recommendation_with_rag(profile, user_id)
                session["conversation_history"].append({"role": "assistant", "text": rec})
                session["recommendation_sent"] = True
                return create_message(user_id=user_id, text=rec)

            return await _ask_next(session, user_id, profile)

        dynamic_map = session.get("dynamic_button_map", {})
        if interactive_id and interactive_id in dynamic_map:
            if interactive_id == "other_freetext":
                session["conversation_history"].append({"role": "user", "text": "[Selected: Other]"})
                reply = "Sure! Please type your answer and I'll use that."
                session["conversation_history"].append({"role": "assistant", "text": reply})
                return create_message(user_id=user_id, text=reply)

            selected_value = dynamic_map[interactive_id]
            # Find the last assistant question to give context to the profile builder
            last_question = ""
            for entry in reversed(session["conversation_history"]):
                if entry["role"] == "assistant" and not entry["text"].startswith("["):
                    last_question = entry["text"]
                    break
            # Inject as a natural answer with context so profile builder can parse it correctly
            contextual_answer = f"{last_question} — {selected_value}"
            session["conversation_history"].append({"role": "user", "text": contextual_answer})
            update_profile_from_history(session, user_id)
            profile = active_profile(session)

            if enough_info(profile):
                rec = build_recommendation_with_rag(profile, user_id)
                session["conversation_history"].append({"role": "assistant", "text": rec})
                session["recommendation_sent"] = True
                return create_message(user_id=user_id, text=rec)

            return await _ask_next(session, user_id, profile)

        return create_message(
            user_id=user_id,
            text="Sorry, I didn't understand that selection. Could you type your answer instead?"
        )

    # --- Voice/audio messages ---
    if isinstance(event, AudioEvent):
        user_id = event.user_id
        session = get_session(user_id)
        try:
            media_uri = media_uri_from_event(event.raw)
            if not media_uri:
                return create_message(user_id=user_id, text="I couldn't access your voice message. Could you type your message instead?")
            audio_bytes = download_media(media_uri)
            import openai, tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
                f.write(audio_bytes)
                tmp_path = f.name
            with open(tmp_path, "rb") as audio_file:
                transcript = openai.audio.transcriptions.create(model="whisper-1", file=audio_file)
            os.unlink(tmp_path)
            transcribed_text = transcript.text.strip()
            if not transcribed_text:
                return create_message(user_id=user_id, text="I couldn't understand your voice message. Could you type your message instead?")
            print(f"[DEBUG] Audio transcribed: {transcribed_text}")
            event = TextEvent(user_id=user_id, text=transcribed_text)
        except Exception as e:
            print(f"[DEBUG] Audio error: {e}")
            return create_message(user_id=user_id, text="I'm having trouble with voice messages right now. Could you type your message instead?")

    # --- Text messages ---
    if not isinstance(event, TextEvent):
        return None

    user_id = event.user_id
    user_message = event.text.strip()
    session = get_session(user_id)

    if not session["greeted"]:
        session["greeted"] = True
        session["conversation_history"].append({"role": "assistant", "text": INTRO_MESSAGE})
        return create_message(user_id=user_id, text=INTRO_MESSAGE)

    if not user_message:
        return create_message(user_id=user_id, text="Please tell me a little more so I can help.")

    # If recommendations already sent, route post-recommendation messages
    if session.get("recommendation_sent"):
        route = classify_post_recommendation(user_message, user_id, session)
        print(f"[DEBUG] Post-recommendation route: {route}")

        if route == "legal":
            session["conversation_history"].append({"role": "user", "text": user_message})
            session["conversation_history"].append({"role": "assistant", "text": LEGAL_RESPONSE})
            return create_message(user_id=user_id, text=LEGAL_RESPONSE)
        if route == "other":
            session["conversation_history"].append({"role": "user", "text": user_message})
            session["conversation_history"].append({"role": "assistant", "text": OUT_OF_SCOPE_RESPONSE})
            return create_message(user_id=user_id, text=OUT_OF_SCOPE_RESPONSE)
        if route == "new_profile":
            session["conversation_history"].append({"role": "user", "text": user_message})
            clarification = "It sounds like someone else needs help too! Are you looking for resources for yourself, or for a friend or family member?"
            session["conversation_history"].append({"role": "assistant", "text": clarification})
            session["awaiting_profile_clarification"] = True
            return create_buttoned_message(
                user_id=user_id,
                text=clarification,
                buttons=[
                    {"id": "profile_self", "title": "For myself"},
                    {"id": "profile_other", "title": "For someone else"},
                ]
            )
        # "followup" or "employment" — answer conversationally
        history_str = format_conversation_history(session["conversation_history"][-10:])
        followup = client.generate(
            model=MODEL_NAME,
            system=FOLLOWUP_PROMPT,
            query=(
                f"CONVERSATION SO FAR:\n{history_str}\n\n"
                f"User's latest message: {user_message}"
            ),
            temperature=0.3,
            lastk=LAST_K,
            session_id=f"{user_id}_followup",
            rag_usage=False,
            websearch=True
        )
        reply = followup.get("result", "").strip()
        if not reply:
            reply = "That's a great question! I'd recommend reaching out directly to the organization — they'll be able to walk you through exactly what to expect next."
        if "http" in reply:
            reply = remove_dead_links(reply)
            reply = verify_recommendations(reply)
        if not reply:
            reply = "I found some resources but couldn't verify their links. Please try MassHire Greater Boston at https://masshireboston.org/ for more options."
        session["conversation_history"].append({"role": "user", "text": user_message})
        session["conversation_history"].append({"role": "assistant", "text": reply})
        return create_message(user_id=user_id, text=reply)

    # Scope check during intake
    scope = classify_scope(user_message, user_id, session)
    if scope == "legal":
        session["conversation_history"].append({"role": "user", "text": user_message})
        session["conversation_history"].append({"role": "assistant", "text": LEGAL_RESPONSE})
        return create_message(user_id=user_id, text=LEGAL_RESPONSE)
    if scope == "other":
        session["conversation_history"].append({"role": "user", "text": user_message})
        session["conversation_history"].append({"role": "assistant", "text": OUT_OF_SCOPE_RESPONSE})
        return create_message(user_id=user_id, text=OUT_OF_SCOPE_RESPONSE)

    # Third-party check
    if session.get("onboarding_step") == "done" and not session.get("awaiting_profile_clarification"):
        missing = get_missing_fields(active_profile(session))
        if not missing:
            third_party = classify_third_party(user_message, user_id)
            if third_party == "other":
                session["awaiting_profile_clarification"] = True
                clarification = "It sounds like you might be asking about someone else. Are you looking for resources for yourself, or for a friend or family member?"
                session["conversation_history"].append({"role": "user", "text": user_message})
                session["conversation_history"].append({"role": "assistant", "text": clarification})
                return create_buttoned_message(
                    user_id=user_id,
                    text=clarification,
                    buttons=[
                        {"id": "profile_self", "title": "For myself"},
                        {"id": "profile_other", "title": "For someone else"},
                    ]
                )
    elif session.get("awaiting_profile_clarification"):
        session["awaiting_profile_clarification"] = False
        if any(w in user_message.lower() for w in ["someone else", "friend", "family", "sister", "brother", "spouse", "husband", "wife", "parent"]):
            session["profiles"].append(new_profile())
            session["active_profile_index"] = len(session["profiles"]) - 1

    session["conversation_history"].append({"role": "user", "text": user_message})
    update_profile_from_history(session, user_id)
    profile = active_profile(session)

    if enough_info(profile):
        rec = build_recommendation_with_rag(profile, user_id)
        session["conversation_history"].append({"role": "assistant", "text": rec})
        session["recommendation_sent"] = True
        return create_message(user_id=user_id, text=rec)

    return await _ask_next(session, user_id, profile)


# ----------------------------
# Terminal fallback
# ----------------------------
if __name__ == '__main__':
    print("Type EXIT to stop.\n")
    print(INTRO_MESSAGE)
    session = get_session("terminal_user")
    session["greeted"] = True
    session["conversation_history"].append({"role": "assistant", "text": INTRO_MESSAGE})

    while True:
        user_message = input("User: ").strip()
        if user_message.lower() == "exit":
            break
        if not user_message:
            print("\nAssistant: Please tell me a little more so I can help.\n")
            continue

        scope = classify_scope(user_message, "terminal_user", session)
        if scope == "legal":
            print(f"\nAssistant: {LEGAL_RESPONSE}\n")
            continue
        if scope == "other":
            print(f"\nAssistant: {OUT_OF_SCOPE_RESPONSE}\n")
            continue

        session["conversation_history"].append({"role": "user", "text": user_message})
        update_profile_from_history(session, "terminal_user")
        profile = active_profile(session)

        if enough_info(profile):
            rec = build_recommendation_with_rag(profile, "terminal_user")
            print(f"\nAssistant: {rec}\n")
            continue

        next_question = get_next_question_from_llm(profile, session["conversation_history"], "terminal_user")
        session["conversation_history"].append({"role": "assistant", "text": next_question})
        print(f"\nAssistant: {next_question}\n")