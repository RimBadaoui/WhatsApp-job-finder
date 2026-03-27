from llmproxy import LLMProxy

if __name__ == '__main__':

    client = LLMProxy()

    response = client.upload_text(
        text="""
        AURA is an autonomous underwater research assistant designed to study deep-sea ecosystems.
        Equipped with advanced sensors and adaptive navigation algorithms,
        AURA can map ocean trenches, analyze water composition, and record marine life activity.
        The project was developed to improve understanding of climate-related changes
        in fragile deep-sea environments.
        """,
        session_id="GenericSession",
        strategy="smart",
    )

    print(response)
