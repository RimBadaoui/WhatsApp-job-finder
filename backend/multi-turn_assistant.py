from llmproxy import LLMProxy
import json

# ----------------------------
# LLM setup
# ----------------------------
client = LLMProxy()

MODEL_NAME = "4o-mini"
TEMPERATURE = 0.0
LAST_K = 10
SESSION_ID = "conversation"

# ----------------------------
# Intro message
# ----------------------------
INTRO_MESSAGE = """
Assistant: Hi! I’m an employment support chatbot for immigrants in Greater Boston.

I can help you find:
- job resources
- workforce training programs
- resume help
- local organizations that support employment

I give general information based on trusted resources.
I’m not a lawyer, so I can’t give legal advice about visas, immigration status, or work authorization.
I also won’t ask for sensitive information like Social Security numbers or passport numbers.

I’ll ask a few short questions so I can suggest resources that may fit your needs.
"""

# ----------------------------
# User profile schema
# ----------------------------
profile = {
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

# Track question flow in Python
asked_fields = []
current_question_field = None
last_question_text = None

# ----------------------------
# Prompt for profile updating
# ----------------------------
PROFILE_BUILDER_PROMPT = '''
You are a profile builder for a multilingual employment-resource chatbot that supports immigrants and immigrant families in Greater Boston.

Your task is to update the user's structured employment profile based on:
1. the current profile
2. the assistant's last question field
3. the assistant's last question text
4. the user's latest message

Only extract information the user explicitly states or clearly implies.
Do not guess.
Preserve existing values unless the user provides new conflicting information.
Return only valid JSON.

Important rules:
- Use LAST_ASKED_FIELD as the strongest clue for how to interpret short answers like "yes", "no", "beginner", "Boston", or "retail".
- If the latest user message is a short answer to the last asked question, update that field directly.
- Do not move a short answer to some other unrelated field unless the user clearly says more.
- If the user says "no" to work_experience, set work_experience to "no prior work experience".
- If the user says "yes" to needs_training, set needs_training to true.
- If the user says "no" to needs_training, set needs_training to false.
- If the user says "yes" to has_resume, set has_resume to "yes".
- If the user says "no" to has_resume, set has_resume to "no".
- Keep open_questions as an empty list; the Python program decides what to ask next.

Normalization rules:
- preferred_language: short value like "English", "Spanish", "Portuguese", "Haitian Creole"
- location: broad place like "Boston", "Chelsea", "East Boston", "Somerville", "Greater Boston"
- employment_goal: short summary like "find a job", "find job training", "resume help"
- job_interests: list of job types or industries
- work_experience: short summary like "retail experience", "cleaning experience", "no prior work experience"
- english_level: "beginner", "intermediate", or "advanced"
- transportation_access: short value like "has car", "public transit only", "limited transportation", "no transportation"
- availability: short value like "full-time", "part-time", "either"
- has_resume: short value like "yes", "no", "needs help making one"

If the user says "I need a job" or something similar, set employment_goal to "find a job".

Return the full updated JSON object and nothing else.

Schema:
{
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

# ----------------------------
# Prompt for final recommendation with RAG + guardrails
# ----------------------------
RECOMMENDATION_PROMPT = '''
You are an AI assistant designed to help immigrants in the Greater Boston area find employment resources, job opportunities, and workforce training programs.

Your goal is to provide helpful, accurate, and safe guidance.

You must follow these rules:

1. DO NOT provide legal advice about immigration status, visas, asylum, green cards, or work authorization.
2. DO NOT tell undocumented users definitively whether they can or cannot work.
3. DO NOT make up information. Only provide information supported by the retrieved trusted sources. If the retrieved context does not support something, say so clearly.
4. If you are unsure, say "I’m not sure" and suggest a trusted organization or resource.
5. DO NOT ask for sensitive personal information such as Social Security numbers, passport numbers, or detailed legal status.
6. Keep responses simple, clear, supportive, and easy to understand.
7. Stay focused on employment-related support such as jobs, training, resume help, workforce programs, and employment-related organizations.
8. If a question is outside your scope, politely say: "I focus on employment support, but I can still try to give general advice based on what information is available."
9. Do not guarantee outcomes or make promises.
10. Always prioritize user safety and trust.

Core guardrails:
- No hallucination: only recommend organizations, programs, benefits, or eligibility details that are supported by the retrieved context.
- If the retrieved context is missing or unclear, say: "I’m not sure about that" or "Let me connect you to a trusted resource."
- No legal advice: if the user asks about visas, green cards, asylum, undocumented status, or whether they are allowed to work, give only general non-legal guidance, include a brief disclaimer, and redirect to a trusted organization.
- No assumptions: do not assume the user's immigration status or legal situation.
- No judgment: use neutral, respectful language.
- Avoid bureaucratic language.

When relevant, suggest local organizations such as MassHire, JVS Boston, or the International Institute of New England, but only if they are supported by the retrieved context.

If the user may need legal help, encourage them to contact a qualified immigration attorney or trusted organization.

Use the retrieved context as your main source of truth.

Your response should:
1. Briefly acknowledge the user's situation.
2. Recommend 2-4 relevant resources, programs, or organizations.
3. For each one, explain why it matches the user's profile.
4. Give a short "next steps" section.
5. If needed, include a brief disclaimer that this is general information, not legal advice.
6. Be concise but useful.

If the user's English level is beginner, prioritize beginner-friendly or language-supportive resources when possible.
If the user needs training, prioritize training and workforce development programs.
If the user has no resume, mention resume help if the retrieved context supports it.
If the user has transportation constraints, prefer nearby or transit-accessible options when the retrieved context supports it.

Do not output JSON.
'''

# ----------------------------
# Question flow handled in Python
# ----------------------------
QUESTION_ORDER = [
    "job_interests",
    "location",
    "preferred_language",
    "english_level",
    "work_experience",
    "transportation_access",
    "availability",
    "has_resume",
    "needs_training"
]

QUESTIONS = {
    "job_interests": "What kind of job are you interested in?",
    "location": "What area do you live in or want to work in?",
    "preferred_language": "What language do you prefer to use with me?",
    "english_level": "How comfortable are you with English at work: beginner, intermediate, or advanced?",
    "work_experience": "Do you have any past work experience?",
    "transportation_access": "Do you have a car, public transit, or limited transportation?",
    "availability": "Are you looking for full-time, part-time, or either?",
    "has_resume": "Do you already have a resume, or do you need help making one?",
    "needs_training": "Would job training or help building skills be useful for you? You can say yes or no."
}

# ----------------------------
# Helpers
# ----------------------------
def safe_json_load(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def merge_profile(current_profile, new_profile):
    merged = current_profile.copy()
    for key, value in new_profile.items():
        if key not in merged:
            continue
        if value is None:
            continue
        merged[key] = value
    return merged


def enough_info(profile_dict):
    required_checks = [
        bool(profile_dict["job_interests"]),
        bool(profile_dict["location"]),
        bool(profile_dict["preferred_language"]),
        bool(profile_dict["english_level"]),
        profile_dict["work_experience"] is not None,
        profile_dict["transportation_access"] is not None,
        profile_dict["availability"] is not None,
        profile_dict["has_resume"] is not None,
        profile_dict["needs_training"] is not None
    ]
    return all(required_checks)


def get_next_question(profile_dict, asked_fields_list):
    for field in QUESTION_ORDER:
        if field in asked_fields_list:
            continue

        if field == "job_interests" and not profile_dict["job_interests"]:
            return field, QUESTIONS[field]

        if field != "job_interests" and profile_dict[field] is None:
            return field, QUESTIONS[field]

    return None, None


def print_profile(profile_dict):
    print("\nCurrent profile:")
    print(json.dumps(profile_dict, indent=2, ensure_ascii=False))


def build_profile_summary(profile_dict):
    return (
        f"Preferred language: {profile_dict['preferred_language'] or 'Unknown'}\n"
        f"Location: {profile_dict['location'] or 'Unknown'}\n"
        f"Employment goal: {profile_dict['employment_goal'] or 'Unknown'}\n"
        f"Job interests: {', '.join(profile_dict['job_interests']) if profile_dict['job_interests'] else 'Unknown'}\n"
        f"Work experience: {profile_dict['work_experience'] or 'Unknown'}\n"
        f"English level: {profile_dict['english_level'] or 'Unknown'}\n"
        f"Transportation access: {profile_dict['transportation_access'] or 'Unknown'}\n"
        f"Needs nearby work: {profile_dict['needs_nearby_work']}\n"
        f"Needs remote work: {profile_dict['needs_remote_work']}\n"
        f"Needs training: {profile_dict['needs_training']}\n"
        f"Needs worker rights help: {profile_dict['needs_worker_rights_help']}\n"
        f"Availability: {profile_dict['availability'] or 'Unknown'}\n"
        f"Has resume: {profile_dict['has_resume'] or 'Unknown'}"
    )


def looks_like_legal_question(user_message: str) -> bool:
    text = user_message.lower()
    triggers = [
        "visa",
        "green card",
        "am i allowed to work",
        "can i work",
        "asylum",
        "undocumented",
        "work authorization",
        "legal status",
        "papers"
    ]
    return any(trigger in text for trigger in triggers)


def build_recommendation_with_rag(profile_dict):
    """
    Uses the uploaded files in the same session via LLMProxy RAG.
    Assumes your proxy will retrieve from files attached to this session
    when rag_usage=True.
    """
    profile_summary = build_profile_summary(profile_dict)

    recommendation = client.generate(
        model=MODEL_NAME,
        system=RECOMMENDATION_PROMPT,
        query=(
            "Use the retrieved documents and the user profile below to recommend relevant employment resources in Greater Boston.\n\n"
            "USER PROFILE:\n"
            f"{profile_summary}\n\n"
            "Focus on programs, organizations, job resources, training opportunities, and next steps that fit this user.\n"
            "If the retrieved context does not support a recommendation, do not make it up.\n"
        ),
        temperature=TEMPERATURE,
        lastk=LAST_K,
        session_id=SESSION_ID,
        rag_usage=True
    )

    return recommendation["result"]


# ----------------------------
# Main terminal loop
# ----------------------------
if __name__ == '__main__':
    print("Type EXIT to stop.\n")
    print(INTRO_MESSAGE)

    while True:
        user_message = input("User: ").strip()

        if user_message.lower() == "exit":
            break

        if not user_message:
            print("\nAssistant: Please tell me a little more so I can help.\n")
            continue

        # Extra safety check for legal/work authorization questions
        if looks_like_legal_question(user_message):
            print(
                "\nAssistant: I can share general employment resources, but I can’t give legal advice about immigration status, visas, or work authorization. "
                "For trusted help, it may be best to contact a qualified immigration attorney or a local organization such as the International Institute of New England.\n"
            )
            continue

        # Update profile from latest message
        profile_builder = client.generate(
            model=MODEL_NAME,
            system=PROFILE_BUILDER_PROMPT,
            query=(
                "Update the user profile based on the current profile, the assistant's last question, and the latest user message.\n\n"
                f"CURRENT_PROFILE_JSON:\n{json.dumps(profile, ensure_ascii=False)}\n\n"
                f"LAST_ASKED_FIELD:\n{current_question_field}\n\n"
                f"LAST_ASSISTANT_QUESTION:\n{last_question_text}\n\n"
                f"LATEST_USER_MESSAGE:\n{user_message}\n\n"
                "Return only the full updated JSON object."
            ),
            temperature=TEMPERATURE,
            lastk=LAST_K,
            session_id=SESSION_ID,
            rag_usage=False
        )

        parsed = safe_json_load(profile_builder["result"])

        if parsed is None:
            print("\n[Warning] Could not parse model output as JSON. Keeping previous profile.")
            print("Raw model output:")
            print(profile_builder["result"])
        else:
            profile = merge_profile(profile, parsed)

        # print_profile(profile)

        # If enough information is collected, move to RAG recommendation step
        if enough_info(profile):
            recommendation_text = build_recommendation_with_rag(profile)
            print("\nAssistant:", recommendation_text, "\n")
            continue

        # Ask next intake question
        next_field, next_question = get_next_question(profile, asked_fields)

        if next_field is None or next_question is None:
            recommendation_text = build_recommendation_with_rag(profile)
            print("\nAssistant:", recommendation_text, "\n")
            continue

        current_question_field = next_field
        last_question_text = next_question

        if next_field not in asked_fields:
            asked_fields.append(next_field)

        print(f"\nAssistant: {next_question}\n")