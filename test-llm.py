#test memory
from app.core.infrastructure import shared_memory_manager

memories = shared_memory_manager.get_user_memories()

print(memories)


#Test LLm

from agno.models.groq import Groq
from agno.models.message import Message

model = Groq(id="llama-3.1-8b-instant")

response = model.invoke(
    messages=[Message(role="user", content="Say hello")],
    assistant_message=Message(role="assistant")
)

print(response.content)

#Test Postgres
from app.core.infrastructure import shared_memory_manager

print(shared_memory_manager.db)