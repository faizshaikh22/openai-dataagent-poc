# Data Agent POC

This project is a Proof-of-Concept for a sophisticated **In-House Data Agent** capable of answering complex data questions by reasoning over schemas, documentation, and user corrections. It mimics the architecture of the OpenAI Data Agent described in their blog.

## 🚀 Features

*   **Multi-Layer Context:**
    *   **Schema Grounding:** Dynamically reads SQLite schema (currently `payroll.db` from NYC Open Data).
    *   **Documentation:** Searches `docs/` for business logic (e.g., "Fiscal Year", "Overtime Pay").
    *   **Memory:** Persists user corrections (e.g., "Manhattan = Borough 'M'").
*   **Self-Correction Loop:**
    *   Generates SQL -> Checks Result -> Fixes Syntax/Logic Errors automatically.
    *   Example: Handles casting string columns (`$219,773.00`) to floats for aggregation.
*   **Ambiguity Resolution:**
    *   Asks clarifying questions if a term is vague (e.g., "Do you mean oldest or newest?").
*   **Simple Web UI:**
    *   Chat interface with markdown rendering and toggleable "Reasoning Trace" to see the agent's thoughts.

## 🛠️ Setup

### Prerequisites
-   Python 3.12+
-   `pip`
-   NVIDIA API Key (or OpenAI API Key if updated)

### Installation

1.  **Install Dependencies:**
    ```bash
    pip install fastapi uvicorn pydantic requests kagglehub pandas python-dotenv
    ```

2.  **Set Environment Variable:**
    ```bash
    export NVIDIA_API_KEY="your_api_key_here"
    ```

3.  **Ingest Data:**
    This script downloads the NYC Payroll dataset (first 20k rows) and creates `payroll.db`.
    ```bash
    python3 ingest_kaggle_data.py
    ```

4.  **Run the Server:**
    ```bash
    python3 main.py
    ```

5.  **Access the UI:**
    Open `http://localhost:8000` in your browser.

## 🧪 Testing & Evaluation

### Manual Testing
Use the UI to ask questions like:
-   "Who has the highest base salary?" (Tests aggregation & casting)
-   "Show me the top 3 overtime earners." (Tests sorting)
-   "When I say Manhattan, filter by borough 'M'." -> "Show top earners in Manhattan." (Tests Memory)

### Automated Evaluation
Run the evaluation suite to check against known "Golden SQL" queries:
```bash
python3 run_evals.py
```
*Note: The evaluator compares SQL results. Since the agent is smart enough to clean data (remove '$'), its results might differ from a naive golden query, which is expected behavior.*

## 📂 Project Structure

-   `agent.py`: Core logic for the LLM agent and reasoning loop.
-   `tools.py`: Helper functions for SQL, Docs, and Memory.
-   `main.py`: FastAPI backend.
-   `ingest_kaggle_data.py`: ETL script for Kaggle data.
-   `static/index.html`: Frontend UI.
-   `docs/`: Markdown files for business context.
-   `run_evals.py`: Evaluation framework.
-   `TEST_CASES.md`: Detailed test scenarios.
