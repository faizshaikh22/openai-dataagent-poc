import sqlite3
import json
import os

DB_FILE = "payroll.db"
CONTEXT_FILE = "schema_context.json"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def get_schema_info():
    """
    Returns a string containing the SQL CREATE TABLE statements
    combined with manual descriptions from schema_context.json.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get raw SQL schema
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='payroll';")
    result = cursor.fetchone()
    create_table_sql = result['sql'] if result else "Table 'payroll' not found."
    
    conn.close()

    # Get manual context
    manual_context = {}
    if os.path.exists(CONTEXT_FILE):
        try:
            with open(CONTEXT_FILE, "r") as f:
                manual_context = json.load(f)
        except Exception as e:
            print(f"Error reading context file: {e}")

    # Combine them
    context_str = f"### Database Schema (SQL)\n{create_table_sql}\n\n"
    
    if "payroll" in manual_context:
        table_info = manual_context["payroll"]
        context_str += f"### Table 'payroll' Description\n{table_info.get('description', '')}\n\n"
        context_str += "### Column Descriptions\n"
        for col, desc in table_info.get("columns", {}).items():
            context_str += f"- **{col}**: {desc}\n"

    return context_str

def execute_query(sql_query: str):
    """
    Executes a read-only SQL query and returns the results.
    """
    # Simple safety check - this is a POC, but we should prevent DROP/DELETE
    forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE"]
    if any(word in sql_query.upper() for word in forbidden):
        return {"error": "Write operations are not allowed in this POC."}

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        
        # Get column names
        columns = [description[0] for description in cursor.description]
        
        data = [dict(row) for row in rows]
        conn.close()
        
        return {"columns": columns, "data": data}
    except Exception as e:
        return {"error": str(e)}
