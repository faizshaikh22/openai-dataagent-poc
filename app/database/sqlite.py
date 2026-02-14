import sqlite3
import os
import json
from app.database.adapter import DatabaseAdapter
from app.database.inspector import DatabaseInspector

# Correct path relative to project root
DB_FILE = "data/payroll.db"
CONTEXT_FILE = "schema_context.json"

class SQLiteAdapter(DatabaseAdapter):
    def __init__(self):
        self.inspector = DatabaseInspector(DB_FILE)

    def _get_connection(self):
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        return conn

    def get_schema(self, table_name: str) -> str:
        return self.inspector.get_table_schema(table_name)

    def execute_query(self, query: str):
        forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE"]
        if any(word in query.upper() for word in forbidden):
            return {"error": "Write operations are not allowed in this POC."}

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            
            columns = [description[0] for description in cursor.description]
            data = [dict(row) for row in rows]
            conn.close()
            
            return {"columns": columns, "data": data}
        except Exception as e:
            return {"error": str(e)}

    def get_rich_context(self) -> str:
        # 1. Automated Context
        context_str = self.inspector.get_full_context("payroll")
        
        # 2. Manual Context
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

# Singleton instance
db_adapter = SQLiteAdapter()
