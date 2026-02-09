import sqlite3
import json
import os
import glob
import pandas as pd

DB_FILE = "payroll.db"
MEMORY_FILE = "memory.json"
DOCS_DIR = "docs"

def get_schema():
    """Returns the database schema formatted for the LLM."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    schema_str = []

    # Get tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    for table in tables:
        table_name = table[0]
        schema_str.append(f"Table: {table_name}")

        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        for col in columns:
            # col[1] is name, col[2] is type
            schema_str.append(f"  - {col[1]} ({col[2]})")
        schema_str.append("")

    conn.close()
    return "\n".join(schema_str)

def run_sql(query):
    """Executes a SQL query and returns the results."""
    # Basic safety: prevent modification (POC level)
    if not query.strip().upper().startswith("SELECT"):
        return "Error: Only SELECT queries are allowed."

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [description[0] for description in cursor.description]
        results = cursor.fetchall()
        conn.close()

        # Format as list of dicts or just a string table
        if not results:
            return "No results found."

        # Return a limited number of rows to avoid context overflow, or summary
        formatted = [f"{columns}"]
        for row in results[:20]: # Limit to 20 rows
            formatted.append(str(row))

        if len(results) > 20:
            formatted.append(f"... ({len(results) - 20} more rows)")

        return "\n".join(formatted)

    except sqlite3.Error as e:
        return f"SQL Error: {e}"

def search_docs(query):
    """Simple keyword search in the docs directory."""
    results = []
    query_terms = query.lower().split()

    for filepath in glob.glob(os.path.join(DOCS_DIR, "*.md")):
        with open(filepath, "r") as f:
            content = f.read()
            # Simple scoring: count term matches
            score = sum(content.lower().count(term) for term in query_terms)
            if score > 0:
                results.append(f"--- From {os.path.basename(filepath)} ---\n{content}\n")

    if not results:
        return "No relevant documentation found."

    return "\n".join(results)

def read_memory():
    """Reads the shared memory file."""
    if not os.path.exists(MEMORY_FILE):
        return []
    try:
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def update_memory(text):
    """Adds a new item to memory."""
    memories = read_memory()
    if text not in memories:
        memories.append(text)
        with open(MEMORY_FILE, "w") as f:
            json.dump(memories, f)
        return "Memory updated."
    return "Memory already exists."
