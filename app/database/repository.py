import sqlite3
import pandas as pd
from app.database.inspector import DatabaseInspector
import os

DB_FILE = "payroll.db"
CONTEXT_FILE = "schema_context.json"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def execute_query(sql_query: str):
    """
    Executes a read-only SQL query and returns the results.
    """
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

def get_rich_context():
    """
    Combines SQL schema, manual descriptions, AND introspected data samples.
    """
    inspector = DatabaseInspector(DB_FILE)
    
    # 1. Start with the automated inspection (Schema + Samples)
    context_str = inspector.get_full_context("payroll")
    
    # 2. Add manual overrides from schema_context.json
    import json
    manual_context = {}
    if os.path.exists(CONTEXT_FILE):
        try:
            with open(CONTEXT_FILE, "r") as f:
                manual_context = json.load(f)
        except Exception as e:
            print(f"Error reading context file: {e}")

    if "payroll" in manual_context:
        table_info = manual_context["payroll"]
        context_str += f"\n\n### Additional Context (Human Notes)\n{table_info.get('description', '')}\n"
        context_str += "Column Definitions:\n"
        for col, desc in table_info.get("columns", {}).items():
            context_str += f"- {col}: {desc}\n"
            
    return context_str
