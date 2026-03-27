from llmproxy import LLMProxy

if __name__ == '__main__':

    client = LLMProxy()
    response = client.retrieve(
        query = 'How do I get to California from Boston?',
        session_id='andrew_session',
        rag_threshold = 0.5,
        rag_k = 5
    )

    print(response)