# Data Agent Architecture

This project implements a "Data Agent" POC inspired by OpenAI's in-house data agent. It uses a ReAct (Reasoning + Acting) loop to answer natural language questions about a dataset.

## System Components

### 1. The Core Agent (`agent.py`)
The `DataAgent` class is the brain of the system.
-   **LLM:** Uses NVIDIA's `moonshotai/kimi-k2.5` model via API.
-   **Loop:** Implements a multi-step reasoning loop (Thought -> Action -> Observation).
-   **Context Window:** Maintains a history of the current session's thoughts and tool outputs.

### 2. Context Layers
The agent relies on three key layers of context to ground its answers:
-   **Schema Layer (`get_schema` in `tools.py`):** Dynamically reads the SQLite database schema (table names, columns, types) and injects it into the system prompt. This ensures the agent never hallucinates column names.
-   **Docs Layer (`search_docs` in `tools.py`):** Allows the agent to search markdown files in `docs/` for business definitions (e.g., "Fiscal Year", "Total Pay"). This handles ambiguity.
-   **Memory Layer (`read_memory`/`update_memory` in `tools.py`):** A simple JSON-based persistent memory. If a user corrects the agent (e.g., "Filter by Borough 'M' when I say Manhattan"), the agent saves this and applies it to future queries.

### 3. Tools (`tools.py`)
The agent has access to a strict set of tools:
-   `run_sql(query)`: Executes read-only SQL queries against `payroll.db`.
-   `search_docs(query)`: Keyword search in documentation.
-   `update_memory(text)`: Stores new facts.
-   `ask_user(question)`: Returns a clarification request to the user.

### 4. Backend (`main.py`)
-   **FastAPI:** Exposes a simple REST API (`POST /chat`) to interact with the agent.
-   **State:** Manages agent instances per session (basic dictionary storage for POC).

### 5. Frontend (`static/index.html`)
-   A lightweight HTML/JS interface that renders Markdown responses and allows users to toggle the "Reasoning Trace" to see the agent's internal thoughts.

## Data Flow

1.  **User Request:** "Who has the highest salary?"
2.  **System Prompt:** Injects Schema + Memories.
3.  **LLM Reasoning:** "I need to check the 'base_salary' column. It might be a string with '$', so I should cast it."
4.  **Tool Execution:** `run_sql("SELECT ...")`
5.  **Observation:** LLM sees the raw result.
6.  **Refinement:** If the SQL fails (e.g., syntax error), the LLM sees the error and retries.
7.  **Final Answer:** Formatted natural language response sent back to the user.

## Limitations & Future Work
-   **Security:** `run_sql` currently has basic checks. A production version needs a read-only DB user and strict parser validation.
-   **Memory:** Currently a single global JSON file. Needs vector-based retrieval for scale.
-   **Context:** Currently injects the *entire* schema. Large schemas would need RAG-based schema selection.
