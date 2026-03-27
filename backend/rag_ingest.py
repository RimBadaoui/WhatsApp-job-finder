import os
from llmproxy import LLMProxy

client = LLMProxy()

EMPLOYMENT_SESSION = "employment_ma"
IMMIGRATION_SESSION = "immigration_work_auth"

EMPLOYMENT_FOLDER = "data/employment"
IMMIGRATION_FOLDER = "data/immigration"

TEXT_EXTENSIONS = {".txt", ".md"}
FILE_EXTENSIONS = {".pdf", ".docx"}


def upload_one_file(file_path, session_id):
    """
    Purpose: Uploads one file to a RAG session.
    Inputs:
             file_path   - String containing the path to the file
             session_id  - String containing the session name
    Output: Returns the upload response
    """
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext in TEXT_EXTENSIONS:
        with open(file_path, "r", encoding="utf-8") as file:
            text = file.read()

        response = client.upload_text(
            text=text,
            session_id=session_id,
            strategy="smart"
        )
        return response

    elif ext in FILE_EXTENSIONS:
        response = client.upload_file(
            file_path=file_path,
            session_id=session_id,
            strategy="smart"
        )
        return response

    else:
        return {"result": "unsupported file type"}


def upload_folder(folder_path, session_id):
    """
    Purpose: Uploads all supported files from a folder into one RAG session.
    Inputs:
             folder_path - String containing the folder location
             session_id  - String containing the session name to upload into
    Output: Returns None
    """
    abs_folder_path = os.path.abspath(folder_path)
    print(f"Checking folder: {abs_folder_path}")

    if not os.path.exists(folder_path):
        print(f"Folder not found: {folder_path}")
        return

    file_list = os.listdir(folder_path)

    if len(file_list) == 0:
        print(f"No files found in: {folder_path}")
        return

    for file_name in file_list:
        file_path = os.path.join(folder_path, file_name)

        if not os.path.isfile(file_path):
            continue

        print(f"Uploading {file_name} to session '{session_id}'...")
        print(f"Full path: {os.path.abspath(file_path)}")

        try:
            response = upload_one_file(file_path, session_id)
            print("Raw response:", response)

            if isinstance(response, dict) and response.get("result") == "An error was encountered":
                print(f"Upload failed for {file_name}.")
            elif isinstance(response, dict) and response.get("result") == "unsupported file type":
                print(f"Skipped unsupported file type: {file_name}")
            else:
                print(f"Upload succeeded for {file_name}.")

        except Exception as error:
            print(f"Upload failed for {file_name}: {error}")

        print("-" * 50)


def main():
    """
    Purpose: Uploads employment and immigration resource files into
             their correct RAG sessions.
    Inputs:  None
    Output: Returns None
    """
    print("Employment folder:", os.path.abspath(EMPLOYMENT_FOLDER))
    print("Immigration folder:", os.path.abspath(IMMIGRATION_FOLDER))
    print()

    print("Uploading employment files...")
    upload_folder(EMPLOYMENT_FOLDER, EMPLOYMENT_SESSION)

    print("\nUploading immigration files...")
    upload_folder(IMMIGRATION_FOLDER, IMMIGRATION_SESSION)

    print("\nDone uploading files.")


if __name__ == "__main__":
    main()