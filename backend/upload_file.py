from llmproxy import LLMProxy

if __name__ == '__main__':

    client = LLMProxy()
    response = client.upload_file(
        file_path = 'cs_handbook.pdf',
        session_id = 'andrew_session',
        strategy = 'smart'
    )

    print(response)