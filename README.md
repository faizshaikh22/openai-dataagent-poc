# OpenAI Data Agent POC

This project is a functional proof-of-concept and template for building an in-house data agent, modeled after the architecture described in OpenAI's blog post:  
**https://openai.com/index/inside-our-in-house-data-agent/**

The goal was to create a portable, template-ready version of the agent that captures the core reasoning, self-correction, and learning capabilities without requiring complex infrastructure like Vector DBs or specific cloud providers.

## Project Overview

### The Plan
The objective was to replicate the "SQL generation" and "Context is Everything" pillars of the OpenAI agent. Specifically:
1.  **Context Enrichment**: Providing the LLM with schema, samples, and human annotations.
2.  **Self-Correction**: An execution loop that catches SQL errors and allows the agent to fix them.
3.  **Memory & Learning**: Systems to remember user corrections and learn from successful queries.
4.  **Evaluation**: A framework to prevent regressions in SQL generation quality.
5.  **Portability**: Using simple file-based storage (SQLite, JSON) so the project can be cloned and adapted immediately.

### What Was Built
We implemented a FastAPI-based agent with the following core components:

*   **Multi-Stage Reasoning Loop**: The agent plans, executes, analyzes errors, retries, and finally visualizes results.
*   **Golden SQL Evaluation Framework**: A testing system that compares generated SQL against "golden" (correct) SQL using structural and result-based metrics.
*   **SQL Memory System**: A system to store and retrieve specific corrections (e.g., "NYPD means Police Department", "Salary fields need text-to-float casting").
*   **Query History & Learning**: The agent logs successful queries to learn common join patterns and filter preferences over time.
*   **Workflow Templates**: A YAML-based system to define reusable, parameterized analysis tasks (e.g., Monthly Payroll Reports).
*   **Persistent Conversations**: Chat history is saved to disk, supporting multi-turn context and follow-up questions.
*   **Web Interface**: A clean, dark-themed UI with a sidebar history, streaming responses, and integrated charting.

## Comparison with OpenAI's Architecture

The following table compares this implementation with the system described in the OpenAI blog.

| Feature | OpenAI Agent | This POC | Notes |
|---------|--------------|----------|-------|
| **SQL Generation** | Yes | Yes | Uses a plan-execute-repair loop. |
| **Context** | Usage, Annotations, Code, Knowledge | Schema, Samples, Annotations, Memory | We focused on schema and explicit memory. |
| **Code Enrichment** | Yes | No | Requires analyzing the specific codebase producing the data. |
| **Memory** | Yes | Yes | Implemented globally and per-user via JSON storage. |
| **Evaluation** | Golden SQL Evals | Golden SQL Evals | Fully implemented regression testing. |
| **Vector Search (RAG)** | Yes | No | Intentionally excluded for portability; context is loaded directly. |
| **Interfaces** | Slack, Web, IDE | Web Only | The backend is API-first and extensible. |
| **Infrastructure** | Complex (Cloud, Vector DB) | Simple (SQLite, JSON) | Designed as a template for easy adoption. |

## Project Structure

*   `app/agent/core.py`: Main logic for the agent (planning, execution, memory retrieval).
*   `app/memory/`: Modules for SQL corrections (`sql_memory.py`) and query history (`query_history.py`).
*   `app/workflows/`: Template engine for reusable YAML workflows.
*   `app/database/`: SQLite adapter and schema inspector.
*   `tests/evals/`: The Golden SQL evaluation runner.
*   `data/`: Stores the SQLite database and JSON memory files.

## Getting Started

### Prerequisites
*   Python 3.10+
*   NVIDIA/OpenAI API Key (configured in `.env`)

### Installation
1.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

2.  Run the application:
    ```bash
    python main.py
    ```
    Access the UI at `http://localhost:8000`.

### Running Evaluations
To verify the agent's SQL generation quality against the test set:

```bash
python run_evals.py
```

## Customization

This project is designed as a template. To use it with your own data:

1.  **Database**: Replace `app/database/sqlite.py` with an adapter for your database (Postgres, Snowflake, etc.).
2.  **Context**: Update `schema_context.json` with descriptions of your tables.
3.  **Tests**: Add your own business-critical questions to `tests/golden_sql/`.
