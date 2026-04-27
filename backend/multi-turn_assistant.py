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
            "greeted": False,
            "onboarding_step": "done",  # language/comfort steps disabled for now
            "awaiting_profile_clarification": False,
            "recommendation_sent": False,  # track whether we've already sent recommendations
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
- If you mention any organization, always include its URL in parentheses.

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

KNOWN VERIFIED URLS — always use these exact URLs for these organizations, never guess or construct alternatives:
- MassHire (any location, any career center): https://masshireboston.org/
- MassHire JobQuest (job listings): https://jobquest.mass.gov/
- Boston Public Library Job Help: https://www.bpl.org/jobs-and-careers/
- International Institute of New England: https://iine.org/
- JVS Boston: https://www.jvs-boston.org/

CRITICAL — follow this order exactly before writing your response:
1. Use web search to find real organizations in Greater Boston that match this user's profile (job interest, location, language, transportation, training needs).
2. From your search results, collect the exact organization name and URL as they appear in the results.
3. Only recommend organizations that appeared in your search results or in the retrieved documents.
4. Use the exact name and URL from the search result — do not alter, guess, or paraphrase organization names or URLs.
5. If a search result does not include a working URL, do not include that organization.
6. Do not recommend any organization you did not find via search or RAG in this session.

Rules:
1. DO NOT provide legal advice about immigration, visas, asylum, green cards, or work authorization.
2. DO NOT make up information. Only recommend organizations confirmed by your search results or retrieved documents.
3. If unsure, say "I'm not sure" and suggest a trusted organization.
4. DO NOT ask for sensitive personal information.
5. Keep responses simple, clear, supportive, and easy to understand.
6. Stay focused on employment support only.
7. Do not guarantee outcomes or make promises.
8. Every resource MUST include its full website URL in parentheses. If you cannot find a verified URL from search results or retrieved documents, do not include that resource.

Personalization rules — you MUST apply ALL of these:
- If the user has a name, address them by name in the opening line.
- Mention their specific job interest (e.g. "nursing", "construction") by name — do not say "your field" generically.
- If they want training, recommend training programs specifically for their job interest.
- If they have limited English, prioritize bilingual or multilingual programs and mention that explicitly.
- If they have limited transportation, only recommend organizations accessible by public transit or remote options.
- If they need a resume, include a specific resume help resource.
- If they are looking for part-time work, say so and filter recommendations accordingly.
- Mention their location (e.g. "in East Boston" or "near Chelsea") when referencing nearby resources.

Your response should:
1. Open with a warm, personalized sentence using their name and specific situation.
2. Recommend 2-4 resources that directly match their job interest, location, and constraints. Format EACH resource exactly like this:
   *Resource Name* (https://full-url-here.org): One sentence explaining why it fits this person specifically.
3. Give 2-3 concrete next steps tailored to their profile.
4. Close with an encouraging line.
5. Include a brief disclaimer if legal topics arose.

Do not output JSON.
'''

VERIFIER_PROMPT = """
You are a fact-checker for an employment resource chatbot.

You will receive a draft response recommending organizations and resources to a job-seeker.

Your job:
1. For each organization or resource mentioned, check if it has a valid, complete URL in parentheses next to it.
2. If a resource has NO URL, remove that resource entirely from the response.
3. If a resource has a malformed or obviously fake URL (e.g. "https://example.com", placeholder text, or a URL that is just a domain root with no relevance), remove that resource.
4. Do not add, invent, or look up any new organizations or URLs.
5. Do not add any new text, lines, or resources that were not in the original response.
6. Do not change any other part of the response — keep the tone, structure, and personalization intact.

Return the corrected response text only. No explanations.
"""

# ----------------------------
# Helpers
# ----------------------------
def _is_dead_url(url: str) -> bool:
    """Return True only if the URL is clearly unreachable or returns a hard error."""
    import socket
    from urllib.parse import urlparse
    try:
        # First check DNS — if the domain doesn't resolve, it's dead
        hostname = urlparse(url).hostname
        if hostname:
            socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return True  # Domain doesn't exist
    try:
        resp = requests.get(url, allow_redirects=True, timeout=8,
                            headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code >= 400:
            return True
        return False
    except requests.RequestException:
        return False  # Network timeout — don't strip, could be a real slow site

def remove_dead_links(text: str) -> str:
    """Find all URLs in text, verify each one, and remove any that are dead or soft-404."""
    urls = re.findall(r'https?://[^\s\)\]"\']+', text)
    for url in set(urls):
        if _is_dead_url(url):
            text = text.replace(url, "")
    # Clean up empty parentheses left behind, e.g. "Name ()" or "Name ( )"
    text = re.sub(r'\(\s*\)', '', text)
    return text.strip()

def verify_recommendations(rec_text: str) -> str:
    """Post-generation verifier: strips any resource that has no valid URL."""
    result = client.generate(
        model=MODEL_NAME,
        system=VERIFIER_PROMPT,
        query=rec_text,
        temperature=0.0,
        lastk=1,
        session_id="verifier",
        rag_usage=False,
        websearch=False  # critical — no web search here or it will hallucinate new URLs
    )
    return result["result"].strip()

def safe_json_load(text: str):
    # Strip markdown code fences if present (e.g. ```json ... ```)
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Remove first and last fence lines
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

# Fields handled by interactive buttons — the LLM should not ask about these as free text
BUTTON_HANDLED_FIELDS = {
    "transportation access (car, public transit, limited)",
    "availability (full-time, part-time, either)",
    "whether they have a resume or need help making one",
    "whether they want job training or skill-building",
}

def get_llm_askable_fields(profile_dict):
    """Return only fields the LLM should ask about as free text (not handled by buttons)."""
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
# Dynamic button generation
# ----------------------------
DYNAMIC_OPTIONS_PROMPT = '''
You are generating quick-reply options for a WhatsApp chatbot helping immigrants find jobs in Greater Boston.

Given a question the bot just asked, generate answer options a user might select.

Rules:
- Generate exactly 2 meaningful options + always add "Other" as the last option (3 total)
- Each option title must be 20 characters or fewer
- Each option must have a unique short id (snake_case, no spaces)
- The last option must always be {"id": "other_freetext", "title": "Other"}
- Only skip buttons entirely if the question is truly open-ended with no reasonable common answers (e.g. "What is your name?")

Return only valid JSON in this format:
{
  "use_buttons": true,
  "question_text": "the question to display",
  "options": [
    {"id": "option_id", "title": "Short Label"},
    {"id": "option_id2", "title": "Short Label 2"},
    {"id": "other_freetext", "title": "Other"}
  ]
}

If buttons are not appropriate, return:
{
  "use_buttons": false,
  "question_text": "the question to display",
  "options": []
}
'''

def generate_dynamic_buttons(question_text: str, user_id: str):
    """Ask the LLM to generate appropriate button options for a given question."""
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
    """Send a question with LLM-generated buttons if appropriate, otherwise plain text."""
    parsed = generate_dynamic_buttons(question_text, user_id)

    if parsed and parsed.get("use_buttons") and parsed.get("options"):
        options = parsed["options"]
        display_text = parsed.get("question_text", question_text)

        # Register dynamic button IDs so the interactive handler can process them
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
            # Use list message for 4-10 options
            return create_list_message(
                user_id=user_id,
                text=display_text,
                button_text="Select an option",
                rows=[{"id": o["id"], "title": o["title"]} for o in options]
            )

    # Fall back to plain text
    return create_message(user_id=user_id, text=question_text)


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

# Fields handled by interactive buttons — the LLM should not ask about these as free text
BUTTON_HANDLED_FIELDS = {
    "transportation access (car, public transit, limited)",
    "availability (full-time, part-time, either)",
    "whether they have a resume or need help making one",
    "whether they want job training or skill-building",
}

def get_llm_askable_fields(profile_dict):
    """Return only fields the LLM should ask about as free text (not handled by buttons)."""
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

def classify_post_recommendation(user_message: str, user_id: str, session: dict) -> str:
    history_str = format_conversation_history(session["conversation_history"][-6:])  # last 3 turns
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
    # During intake, trust all responses as employment-related
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
            "Do not modify, guess, or construct URLs. If you cannot confirm a URL, do not include that resource.\n"
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

    # Fallback: if RAG returns empty, retry with a simpler query and no RAG
    if not raw_result:
        print("[DEBUG] RAG returned empty result — falling back to web search only")
        profile_summary = build_profile_summary(profile_dict)
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

    # If still empty after fallback, return a safe default message
    if not raw_result:
        print("[DEBUG] Fallback also returned empty — returning default message")
        return (
            "I'm sorry, I wasn't able to find specific resources right now. "
            "Please try reaching out to MassHire Greater Boston at https://www.masshiregb.org — "
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
    history_str = format_conversation_history(session["conversation_history"])
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
    # Button-handled fields — send interactive UI with warm bridging text
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

    # All other fields — use LLM for a warm, flowing response with dynamic buttons
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

        # Profile clarification buttons
        if interactive_id == "profile_self":
            session["awaiting_profile_clarification"] = False
            session["recommendation_sent"] = False
            # Switch back to profile index 0 (the original user's profile)
            session["active_profile_index"] = 0
            session["conversation_history"].append({"role": "user", "text": "[Selected: For myself]"})
            profile = active_profile(session)
            # If we already have enough info for this profile, just say so
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
            session["conversation_history"].append({"role": "user", "text": "[Selected: For someone else]"})
            next_q = "Got it! Let me start a new profile for them. What kind of work are they looking for, and where are they located?"
            session["conversation_history"].append({"role": "assistant", "text": next_q})
            return create_message(user_id=user_id, text=next_q)

        if interactive_id and interactive_id in INTERACTIVE_FIELD_MAP:
            field, value = INTERACTIVE_FIELD_MAP[interactive_id]
            session["profiles"][session["active_profile_index"]][field] = value
            session["conversation_history"].append({
                "role": "user",
                "text": f"[Selected: {value}]"
            })
            profile = active_profile(session)

            if enough_info(profile):
                rec = build_recommendation_with_rag(profile, user_id)
                session["conversation_history"].append({"role": "assistant", "text": rec})
                session["recommendation_sent"] = True
                return create_message(user_id=user_id, text=rec)

            return await _ask_next(session, user_id, profile)

        # Handle dynamically generated button responses
        dynamic_map = session.get("dynamic_button_map", {})
        if interactive_id and interactive_id in dynamic_map:
            # "Other" — ask user to type their answer
            if interactive_id == "other_freetext":
                session["conversation_history"].append({"role": "user", "text": "[Selected: Other]"})
                reply = "Sure! Please type your answer and I'll use that."
                session["conversation_history"].append({"role": "assistant", "text": reply})
                return create_message(user_id=user_id, text=reply)

            selected_value = dynamic_map[interactive_id]
            session["conversation_history"].append({
                "role": "user",
                "text": selected_value
            })
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

            # Transcribe using OpenAI Whisper
            import openai, tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
                f.write(audio_bytes)
                tmp_path = f.name
            with open(tmp_path, "rb") as audio_file:
                transcript = openai.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
            os.unlink(tmp_path)
            transcribed_text = transcript.text.strip()

            if not transcribed_text:
                return create_message(user_id=user_id, text="I couldn't understand your voice message. Could you type your message instead?")

            print(f"[DEBUG] Audio transcribed: {transcribed_text}")
            # Reuse text handling by converting to TextEvent
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

    # First message — greeting
    if not session["greeted"]:
        session["greeted"] = True
        session["conversation_history"].append({"role": "assistant", "text": INTRO_MESSAGE})
        return create_message(user_id=user_id, text=INTRO_MESSAGE)

    if not user_message:
        return create_message(user_id=user_id, text="Please tell me a little more so I can help.")

    # Route the message based on context
    if session.get("recommendation_sent"):
        route = classify_post_recommendation(user_message, user_id, session)
    else:
        scope = classify_scope(user_message, user_id, session)
        route = scope  # "employment", "legal", or "other"

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

    # Third-party check — only after intake is complete
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

    # If recommendations already sent, handle as follow-up conversation
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
        # If the follow-up response contains URLs, run it through the same verification pipeline
        if "http" in reply:
            reply = remove_dead_links(reply)
            reply = verify_recommendations(reply)
        if not reply:
            reply = "I found some resources but couldn't verify their links. Please try MassHire Greater Boston at https://masshireboston.org/ for more options."
        session["conversation_history"].append({"role": "user", "text": user_message})
        session["conversation_history"].append({"role": "assistant", "text": reply})
        return create_message(user_id=user_id, text=reply)

    # Update profile
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