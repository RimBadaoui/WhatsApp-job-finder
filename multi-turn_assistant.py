from llmproxy import LLMProxy
from wa_service_sdk import BaseEvent, TextEvent, InteractiveEvent, create_message, create_buttoned_message, create_list_message
import json

# ----------------------------
# LLM setup
# ----------------------------
client = LLMProxy()

MODEL_NAME = "4o-mini"
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

To get started — what language do you prefer?"""

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
            "onboarding_step": "language",  # language -> comfort -> done
            "awaiting_profile_clarification": False,
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

NEXT_QUESTION_PROMPT = '''
You are a warm, conversational employment support assistant helping immigrants in Greater Boston.

You are in the middle of an intake conversation. Your job is to ask ONE question about the FIRST missing field listed below.

Missing fields still needed (ask about the FIRST one only):
{missing_fields}

Rules:
- Ask ONLY about the first field in the list above. Do not ask about any other topic.
- NEVER ask about availability, full-time vs part-time, transportation, resume, or training — those are handled separately with buttons.
- Make it feel natural and conversational, not like a form.
- If the user introduced themselves with a lot of info, acknowledge it warmly first, then ask the question.
- Build on what the user already said when possible.
- Do not repeat questions already answered.
- Do not ask about sensitive legal or immigration status.
- Keep it short and friendly.

Return only the question text, nothing else.
'''

RECOMMENDATION_PROMPT = '''
You are an AI assistant helping immigrants in Greater Boston find employment resources, job opportunities, and workforce training programs.

Rules:
1. DO NOT provide legal advice about immigration, visas, asylum, green cards, or work authorization.
2. DO NOT make up information. Only use information supported by the retrieved sources.
3. If unsure, say "I'm not sure" and suggest a trusted organization.
4. DO NOT ask for sensitive personal information.
5. Keep responses simple, clear, supportive, and easy to understand.
6. Stay focused on employment support only.
7. Do not guarantee outcomes or make promises.
8. Provide direct links if possible.

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
2. Recommend 2-4 resources that directly match their job interest, location, and constraints — explain why each one fits them specifically.
3. Give 2-3 concrete next steps tailored to their profile (e.g. "Since you don't have a resume yet, start with WorkSource Boston's free resume workshop").
4. Close with an encouraging line.
5. Include a brief disclaimer if legal topics arose.

Do not output JSON.
'''

# ----------------------------
# Helpers
# ----------------------------
def safe_json_load(text: str):
    try:
        return json.loads(text)
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
        rag_usage=False
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
        rag_usage=False
    )
    return result["result"].strip().lower()

def build_recommendation_with_rag(profile_dict, user_id):
    profile_summary = build_profile_summary(profile_dict)
    recommendation = client.generate(
        model=MODEL_NAME,
        system=RECOMMENDATION_PROMPT,
        query=(
            "Use the retrieved documents and the user profile below to write a personalized recommendation.\n\n"
            f"USER PROFILE:\n{profile_summary}\n\n"
            "You MUST reference their specific job interest, location, availability, English level, "
            "transportation access, resume status, and training needs in your response. "
            "Do not write a generic response — every recommendation must explain why it fits this specific person.\n"
            "If the retrieved context does not support a recommendation, do not make it up.\n"
        ),
        temperature=TEMPERATURE,
        lastk=LAST_K,
        session_id=user_id,
        rag_usage=True
    )

    print("[DEBUG] Full RAG response keys:", recommendation.keys())
    print("[DEBUG] Full RAG response:", json.dumps(recommendation, indent=2, ensure_ascii=False))
    return recommendation["result"]

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
        rag_usage=False
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
        rag_usage=False
    )
    parsed = safe_json_load(profile_builder["result"])
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
    if not profile.get("job_interests"):
        q = "What kind of work are you looking for? For example: healthcare, construction, retail, cleaning, food service, or something else?"
        session["conversation_history"].append({"role": "assistant", "text": q})
        return create_message(user_id=user_id, text=q)

    if not profile.get("location"):
        q = "What area of Greater Boston are you located in or would like to work in? For example: Boston, Chelsea, East Boston, Somerville, etc."
        session["conversation_history"].append({"role": "assistant", "text": q})
        return create_message(user_id=user_id, text=q)

    if profile.get("work_experience") is None:
        q = "Do you have any previous work experience? If so, what kind of work have you done?"
        session["conversation_history"].append({"role": "assistant", "text": q})
        return create_message(user_id=user_id, text=q)

    if profile.get("transportation_access") is None:
        session["conversation_history"].append({"role": "assistant", "text": "[Sent transportation options]"})
        return transportation_buttons(user_id)

    if profile.get("availability") is None:
        session["conversation_history"].append({"role": "assistant", "text": "[Sent availability options]"})
        return availability_buttons(user_id)

    if profile.get("has_resume") is None:
        session["conversation_history"].append({"role": "assistant", "text": "[Sent resume options]"})
        return resume_buttons(user_id)

    if profile.get("needs_training") is None:
        session["conversation_history"].append({"role": "assistant", "text": "[Sent training options]"})
        return training_buttons(user_id)

    # Fallback
    q = get_next_question_from_llm(profile, session["conversation_history"], user_id)
    session["conversation_history"].append({"role": "assistant", "text": q})
    return create_message(user_id=user_id, text=q)

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
            session["conversation_history"].append({"role": "user", "text": "[Selected: For myself]"})
            return await _ask_next(session, user_id, active_profile(session))

        if interactive_id == "profile_other":
            session["awaiting_profile_clarification"] = False
            session["profiles"].append(new_profile())
            session["active_profile_index"] = len(session["profiles"]) - 1
            session["conversation_history"].append({"role": "user", "text": "[Selected: For someone else]"})
            next_q = "Got it! Let me start a new profile. What kind of work are they looking for, and where are they located?"
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

            # Onboarding: language selected
            if session["onboarding_step"] == "language" and field == "preferred_language":
                session["onboarding_step"] = "comfort"
                session["conversation_history"].append({"role": "assistant", "text": "[Sent English level options]"})
                return english_level_list(user_id)

            # Onboarding: comfort level selected
            if session["onboarding_step"] == "comfort" and field == "english_level":
                session["onboarding_step"] = "done"
                next_q = "Great, thanks! Now tell me a little about yourself — what kind of work are you looking for, and where are you located?"
                session["conversation_history"].append({"role": "assistant", "text": next_q})
                return create_message(user_id=user_id, text=next_q)

            # Normal flow
            if enough_info(profile):
                rec = build_recommendation_with_rag(profile, user_id)
                session["conversation_history"].append({"role": "assistant", "text": rec})
                return create_message(user_id=user_id, text=rec)

            return await _ask_next(session, user_id, profile)

        return create_message(
            user_id=user_id,
            text="Sorry, I didn't understand that selection. Could you type your answer instead?"
        )

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

    # Onboarding: language step
    if session["onboarding_step"] == "language":
        if "english" in user_message.lower():
            session["profiles"][0]["preferred_language"] = "English"
            session["conversation_history"].append({"role": "user", "text": user_message})
            session["onboarding_step"] = "comfort"
            session["conversation_history"].append({"role": "assistant", "text": "[Sent English level options]"})
            return english_level_list(user_id)
        elif "arabic" in user_message.lower():
            session["profiles"][0]["preferred_language"] = "Arabic"
            session["conversation_history"].append({"role": "user", "text": user_message})
            session["onboarding_step"] = "comfort"
            session["conversation_history"].append({"role": "assistant", "text": "[Sent English level options]"})
            return english_level_list(user_id)
        else:
            session["conversation_history"].append({"role": "assistant", "text": "[Sent language options]"})
            return language_buttons(user_id)

    # Onboarding: comfort step
    if session["onboarding_step"] == "comfort":
        for level in ["beginner", "intermediate", "advanced"]:
            if level in user_message.lower():
                session["profiles"][session["active_profile_index"]]["english_level"] = level
                session["conversation_history"].append({"role": "user", "text": user_message})
                session["onboarding_step"] = "done"
                next_q = "Great, thanks! Now tell me a little about yourself — what kind of work are you looking for, and where are you located?"
                session["conversation_history"].append({"role": "assistant", "text": next_q})
                return create_message(user_id=user_id, text=next_q)
        return english_level_list(user_id)

    if not user_message:
        return create_message(user_id=user_id, text="Please tell me a little more so I can help.")

    # Scope check — only run when profile is complete
    scope = classify_scope(user_message, user_id, session)
    if scope == "legal":
        session["conversation_history"].append({"role": "user", "text": user_message})
        session["conversation_history"].append({"role": "assistant", "text": LEGAL_RESPONSE})
        return create_message(user_id=user_id, text=LEGAL_RESPONSE)
    if scope == "other":
        session["conversation_history"].append({"role": "user", "text": user_message})
        session["conversation_history"].append({"role": "assistant", "text": OUT_OF_SCOPE_RESPONSE})
        return create_message(user_id=user_id, text=OUT_OF_SCOPE_RESPONSE)

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

    session["conversation_history"].append({"role": "user", "text": user_message})

    # Update profile
    update_profile_from_history(session, user_id)
    profile = active_profile(session)

    if enough_info(profile):
        rec = build_recommendation_with_rag(profile, user_id)
        session["conversation_history"].append({"role": "assistant", "text": rec})
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