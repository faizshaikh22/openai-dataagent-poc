from agno.agent import Agent
from agno.models.openai import OpenAIChat
from app.core.knowledge import get_knowledge_base
import os

def get_agent(session_id: str = "default"):
    """
    Creates an Agno Agent.
    """
    # Use NVIDIA API if available
    api_key = os.environ.get("NVIDIA_API_KEY")
    base_url = "https://integrate.api.nvidia.com/v1"
    model_id = "moonshotai/kimi-k2.5"

    kb = get_knowledge_base()

    agent = Agent(
        model=OpenAIChat(
            id=model_id,
            api_key=api_key,
            base_url=base_url,
        ),
        knowledge=kb,
        search_knowledge=True,
        # read_chat_history=True, # Might be default or named differently
        # show_tool_calls=True, # Removed
        markdown=True,
        instructions=[
            "You are a helpful assistant with access to a knowledge base.",
            "Always search the knowledge base first before answering.",
            "If the answer is in the knowledge base, cite the source.",
        ],
    )

    return agent
