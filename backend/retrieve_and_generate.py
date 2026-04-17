# from __future__ import annotations
# from llmproxy import LLMProxy
# from string import Template
# from time import sleep
# from wa_service_sdk import (
#     BaseEvent,
#     Button,
#     InteractiveEvent,
#     ReactionEvent,
#     TextEvent,
#     create_buttoned_message,
#     create_message,
# )

# def rag_context_string_simple(rag_context):

#     """
#     Convert the RAG context list (from retrieve API)
#     into a single plain-text string that can be appended to a query.
#     """

#     context_string = ""

#     i=1
#     for collection in rag_context:
    
#         if not context_string:
#             context_string = """The following is additional context that may be helpful in answering the user's query."""

#         context_string += """
#         #{} {}
#         """.format(i, collection['doc_summary'])
#         j=1
#         for chunk in collection['chunks']:
#             context_string+= """
#             #{}.{} {}
#             """.format(i,j, chunk)
#             j+=1
#         i+=1
#     return context_string


# if __name__ == '__main__':

#     client = LLMProxy()

#     # Add several documents to session_id = "RAG"

#     # DOC1
#     client.upload_file(
#         file_path = 'cs_handbook.pdf',
#         session_id = 'andrew_session',
#         strategy = 'smart'
#     )


#     # sleep so documents are added to session_id=RAG
#     sleep(10)

#     # Query used to retrieve relevant context
#     query = 


#     # assuming some document(s) has previously been uploaded to session_id=RAG
#     rag_context = client.retrieve(
#         query =query,
#         session_id='andrew_session',
#         rag_threshold = 0.2,
#         rag_k = 3)
    
#     handle_event(query, TextEvent)

    

#     # print(response)

# async def handle_event(query, event: BaseEvent):
#     # combining query with rag_context
#     query_with_rag_context = Template("$query\n$rag_context").substitute(
#                             query=query,
#                             rag_context=rag_context_string_simple(rag_context))

#     # Pass to LLM using a different session (session_id=GenericSession)
#     # You can also set rag_usage=True to use RAG context from GenericSession
#     response = client.generate(model = '4o-mini',
#         system="Answer questions in a brief and concise manner",
#         query = query_with_rag_context,
#         temperature=0.0,
#         lastk=1,
#         session_id='andrew_session',
#         rag_usage = True
#         )
    

#     if isinstance(event, ReactionEvent):
#         return create_message(
#             user_id=event.user_id,
#             text=f"You reacted: {event.emoji}",
#         )

#     if isinstance(event, InteractiveEvent):
#         return create_message(
#             user_id=event.user_id,
#             text=f"You clicked: {event.interaction_id}",
#         )

#     if not isinstance(event, TextEvent):

#         return create_message(user_id=event.user_id, text={response})

#     normalized = event.text.strip().lower()

#     if normalized in {"hi", "hello"}:
#         return create_buttoned_message(
#             user_id=event.user_id,
#             text="Hello! Pick an option:",
#             buttons=[
#                 Button(id="help", title="Help"),
#                 Button(id="echo", title="Echo"),
#                 Button(id="option3", title="option3"),
#             ],
#         )

#     return create_message(user_id=event.user_id, text=f"You said: {event.text}")



from __future__ import annotations
from llmproxy import LLMProxy
from string import Template
from wa_service_sdk import (
    BaseEvent,
    TextEvent,
    create_message,
)

client = LLMProxy()

def rag_context_string_simple(rag_context):
    context_string = ""
    i = 1
    for collection in rag_context:
        if not context_string:
            context_string = "The following is additional context that may be helpful in answering the user's query."
        context_string += "\n#{} {}".format(i, collection['doc_summary'])
        j = 1
        for chunk in collection['chunks']:
            context_string += "\n#{}.{} {}".format(i, j, chunk)
            j += 1
        i += 1
    return context_string


async def handle_event(event: BaseEvent):
    if not isinstance(event, TextEvent):
        return None

    query = event.text.strip()

    rag_context = client.retrieve(
        query=query,
        session_id='andrew_session',
        rag_threshold=0.2,
        rag_k=3
    )

    query_with_rag_context = f"{query}\n{rag_context_string_simple(rag_context)}"

    response = client.generate(
        model='gemini-2.5-flash-lite',
        system="Answer questions in a brief and concise manner",
        query=query_with_rag_context,
        temperature=0.0,
        lastk=1,
        session_id='andrew_session',
        rag_usage=False,  # we're handling RAG manually via retrieve()
        websearch=True
    )

    return create_message(user_id=event.user_id, text=response['result'])