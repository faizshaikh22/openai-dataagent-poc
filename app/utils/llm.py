import os
import sys

import httpx
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Clear proxy env vars to avoid httpx conflict
for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
    os.environ.pop(var, None)

# Initialize client with explicit httpx client to avoid proxy issues
http_client = httpx.Client(timeout=120.0)

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.environ.get("NVIDIA_API_KEY"),
    http_client=http_client,
)

MODEL = "stepfun-ai/step-3.5-flash"


def query_llm(messages, stream=False):
    """
    Generic wrapper for the LLM.
    If stream=True, returns a generator yielding (type, content).
    Type can be 'reasoning' or 'content'.
    """
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7,  # Slightly creative but focused
            top_p=1,
            max_tokens=8192,
            extra_body={
                "chat_template_kwargs": {
                    "enable_thinking": True,
                    "clear_thinking": False,
                }
            },
            stream=stream,
        )

        if stream:
            return _stream_response(completion)
        else:
            return _collect_response(completion)

    except Exception as e:
        print(f"LLM Error: {e}")
        return None


def _stream_response(completion):
    for chunk in completion:
        if not getattr(chunk, "choices", None):
            continue
        if len(chunk.choices) == 0 or getattr(chunk.choices[0], "delta", None) is None:
            continue

        delta = chunk.choices[0].delta

        # Check for reasoning
        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning:
            yield ("reasoning", reasoning)

        # Check for content
        content = getattr(delta, "content", None)
        if content:
            yield ("content", content)


def _collect_response(completion):
    # For non-streaming, we just want the content (and maybe reasoning if needed, but usually just content for SQL)
    # The NVIDIA API with stream=False returns a standard object
    # But wait, the user example uses stream=True.
    # Let's see if stream=False works with the extra_body params for reasoning.
    # Usually it puts reasoning in the content or a separate field.
    # To be safe and consistent with the user's snippet, I'll use stream=True internally and collect it.

    full_reasoning = ""
    full_content = ""

    # We re-run the create call with stream=True because the helper logic above assumes it.
    # But wait, I can just change the logic in query_llm to always stream and collect if stream=False.
    pass
    # I will refactor query_llm to always stream and handle the collection logic there.


def query_llm_sync(messages):
    """
    Synchronous version that collects all output.
    Returns (reasoning, content) tuple.
    """
    completion = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.1,  # Low temp for code generation
        top_p=1,
        max_tokens=2048,
        extra_body={
            "chat_template_kwargs": {"enable_thinking": True, "clear_thinking": False}
        },
        stream=True,
    )

    reasoning_acc = []
    content_acc = []

    for chunk in completion:
        if not getattr(chunk, "choices", None):
            continue
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        if getattr(delta, "reasoning_content", None):
            reasoning_acc.append(delta.reasoning_content)
        if getattr(delta, "content", None):
            content_acc.append(delta.content)

    return "".join(reasoning_acc), "".join(content_acc)
