import sqlite3
import pandas as pd
from typing import Dict, List, Any

class DatabaseInspector:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_table_schema(self, table_name: str) -> str:
        """
        Returns the CREATE TABLE statement.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            result = cursor.fetchone()
            return result['sql'] if result else ""
        finally:
            conn.close()

    def get_column_stats(self, table_name: str) -> Dict[str, Any]:
        """
        Analyzes columns to find low-cardinality categorical values and samples.
        This helps the LLM understand what values are valid for WHERE clauses.
        """
        conn = self.get_connection()
        try:
            # Get basic info
            df = pd.read_sql_query(f"SELECT * FROM {table_name} LIMIT 1000", conn)
            
            stats = {}
            for col in df.columns:
                # Check for low cardinality (categorical)
                unique_vals = df[col].dropna().unique()
                is_categorical = len(unique_vals) < 50 and df[col].dtype == 'object'
                
                col_info = {
                    "type": str(df[col].dtype),
                    "sample_values": df[col].dropna().head(3).tolist(),
                    "is_categorical": is_categorical,
                    "categories": unique_vals.tolist() if is_categorical else None
                }
                stats[col] = col_info
            return stats
        except Exception as e:
            print(f"Error inspecting table {table_name}: {e}")
            return {}
        finally:
            conn.close()

    def get_full_context(self, table_name: str) -> str:
        """
        Constructs a rich text representation of the table schema + data samples.
        """
        schema = self.get_table_schema(table_name)
        stats = self.get_column_stats(table_name)
        
        context = f"### Table: {table_name}\n"
        context += f"Schema: {schema}\n\n"
        context += "### Column Insights (Use these values for filtering):\n"
        
        for col, info in stats.items():
            context += f"- **{col}** ({info['type']}): "
            if info['is_categorical']:
                # List up to 10 categories
                cats = info['categories'][:10]
                context += f"Possible values: {cats}..." if len(info['categories']) > 10 else f"Values: {cats}"
            else:
                context += f"Sample values: {info['sample_values']}"
            context += "\n"
            
        return context
