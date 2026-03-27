import os
from llmproxy import LLMProxy


def upload_pdf_to_course(client: LLMProxy, path: str, course_session: str) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    return client.upload_file(
        file_path=path,
        session_id=course_session,
        strategy="smart",
    )