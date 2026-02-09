import requests
import json
import os
import re
from tools import get_schema, run_sql, search_docs, read_memory, update_memory

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "moonshotai/kimi-k2.5"

class DataAgent:
    def __init__(self):
        self.schema = get_schema()
        self.max_steps = 10
        self.messages = [] # Use a structured message history

    def _get_system_prompt(self):
        memories = read_memory()
        memory_text = "\n".join([f"- {m}" for m in memories]) if memories else "No memories yet."

        return f"""You are a sophisticated Data Agent. You have access to a SQLite database and documentation.
Your goal is to answer the user's question accurately by querying the database or checking documentation.

**Capabilities & Rules:**
1.  **Schema Grounding:** Use the provided schema exactly. Do not hallucinate columns.
2.  **Docs First:** If a term is ambiguous (e.g. "Gross Revenue"), check `search_docs` first.
3.  **Self-Correction:** If a SQL query fails, read the error, think about why, and try a fixed query.
4.  **Memory:** If the user corrects you (e.g., "Revenue excludes tax"), use `update_memory` to save it. Check "Current Memory" for past corrections.
5.  **Ambiguity:** If the request is vague, ask the user for clarification.

**Tools:**
- `run_sql`: Execute a SQL query. Input: The SQL string (e.g., "SELECT * FROM orders LIMIT 5").
- `search_docs`: Search documentation. Input: Search term (e.g., "Gross Revenue").
- `update_memory`: Save a fact to memory. Input: The fact string.
- `ask_user`: Ask the user for clarification. Input: The question to ask.

**Response Format:**
Use the following format exactly for every step:

Thought: <reasoning about what to do next>
Action: <tool_name>
Action Input: <tool_input>

I will then provide the result as:
Observation: <tool_output>

When you have the answer, respond with:
Final Answer: <your final answer>

**Database Schema:**
{self.schema}

**Current Memory:**
{memory_text}
"""

    def call_llm(self, messages):
        headers = {
            "Authorization": f"Bearer {NVIDIA_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": MODEL,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.1,
            "stop": ["Observation:"] # Stop generation when it's time for an observation
        }

        try:
            response = requests.post(API_URL, headers=headers, json=payload)
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
            return content
        except Exception as e:
            print(f"LLM Error: {e}")
            return "Error calling LLM."

    def run(self, user_input):
        # Start a fresh conversation for this turn, or continue if multi-turn?
        # For POC, let's reset messages per request but keep system prompt fresh.
        # Actually, if we want multi-turn context (TC-12), we should keep messages.

        # Reset messages if it's the first turn, or keep appending?
        # Let's assume stateless per request for simplicity, OR pass session_id.
        # But wait, TC-12 requires context. So I should persist `self.messages`.

        if not self.messages:
            self.messages = [{"role": "system", "content": self._get_system_prompt()}]

        self.messages.append({"role": "user", "content": user_input})

        steps = []
        final_answer = ""

        for i in range(self.max_steps):
            # Call LLM
            response = self.call_llm(self.messages)
            if not response:
                return "Error: Empty response from LLM.", steps

            # Append Assistant response
            self.messages.append({"role": "assistant", "content": response})
            steps.append(response)

            # Parse for Final Answer
            if "Final Answer:" in response:
                final_answer = response.split("Final Answer:")[-1].strip()
                # Clean up history? Maybe keep it for context.
                return final_answer, steps

            # Parse Action
            # Use regex to find the LAST Action/Input pair if multiple (which shouldn't happen with stop sequence)
            action_match = re.search(r"Action:\s*(.+?)\nAction Input:\s*(.+)", response, re.DOTALL)

            if action_match:
                tool_name = action_match.group(1).strip()
                tool_input = action_match.group(2).strip()

                # Execute Tool
                observation_content = ""
                if tool_name == "run_sql":
                    observation_content = run_sql(tool_input)
                elif tool_name == "search_docs":
                    observation_content = search_docs(tool_input)
                elif tool_name == "update_memory":
                    observation_content = update_memory(tool_input)
                elif tool_name == "ask_user":
                    return f"CLARIFICATION REQUIRED: {tool_input}", steps
                else:
                    observation_content = f"Error: Unknown tool '{tool_name}'. Valid tools: run_sql, search_docs, update_memory, ask_user."

                # Append Observation as User message (common ReAct pattern)
                obs_message = f"Observation: {observation_content}"
                self.messages.append({"role": "user", "content": obs_message})
                steps.append(obs_message)
            else:
                # If no action and no final answer, force a thought?
                # Or assume it's chatting.
                if "Thought:" not in response and "Action:" not in response:
                     # Maybe it just answered directly?
                     return response, steps

                # If it had a thought but no action, prompt it to continue
                self.messages.append({"role": "user", "content": "Observation: You didn't provide an Action. Please specify an Action or Final Answer."})

        return "Error: Maximum steps reached.", steps

if __name__ == "__main__":
    agent = DataAgent()
    print("Agent initialized. Type 'quit' to exit.")
    while True:
        try:
            q = input("User: ")
            if q.lower() == 'quit': break
            ans, thoughts = agent.run(q)
            print(f"Agent: {ans}")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")
