# Database Migration Guide

This guide explains how to migrate the Data Agent from SQLite to PostgreSQL, MySQL, or any other SQL database. The architecture is designed to be database-agnostic - only the adapter layer needs to change.

## Architecture Overview

The project uses an **Adapter Pattern** to isolate database-specific logic:

```
app/agent/core.py        -> Calls abstract interface
         |
         v
app/database/adapter.py  -> Abstract Base Class (ABC)
         |
         v
app/database/sqlite.py  -> Concrete implementation (what you replace)
```

## Step-by-Step Migration

### Step 1: Create a New Adapter

Create `app/database/postgres.py` (or mysql.py, etc.):

```python
import os
from typing import Dict, Any, List
from app.database.adapter import DatabaseAdapter

# You would use psycopg2 for PostgreSQL
import psycopg2
from psycopg2.extras import RealDictCursor


class PostgresAdapter(DatabaseAdapter):
    def __init__(self):
        self.connection_params = {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": os.environ.get("DB_PORT", "5432"),
            "dbname": os.environ.get("DB_NAME", "mydb"),
            "user": os.environ.get("DB_USER", "user"),
            "password": os.environ.get("DB_PASSWORD", "password")
        }

    def _get_connection(self):
        """Create a new database connection"""
        return psycopg2.connect(**self.connection_params)

    def execute_query(self, query: str) -> Dict[str, Any]:
        """
        Execute a read-only SQL query and return results.
        
        Returns:
            {"columns": [...], "data": [...]}
        """
        # Security: Block write operations
        forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "CREATE"]
        if any(word.upper() in query.upper() for word in forbidden):
            return {"error": "Write operations are not allowed."}

        try:
            conn = self._get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query)
            
            # Get column names
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            
            # Fetch all results
            rows = cursor.fetchall()
            
            # Convert RealDictRow to dict
            data = [dict(row) for row in rows]
            
            cursor.close()
            conn.close()
            
            return {"columns": columns, "data": data}
            
        except Exception as e:
            return {"error": str(e)}

    def get_schema(self, table_name: str) -> str:
        """Get the CREATE TABLE statement or schema definition"""
        # PostgreSQL approach using information_schema
        query = """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """
        # ... implementation to build schema string

    def get_rich_context(self) -> str:
        """Build comprehensive context about all available tables"""
        # 1. Get all tables
        # 2. Get columns for each table
        # 3. Get sample values
        # 4. Get foreign key relationships
        # ... combine into context string
```

### Step 2: Update the Database Inspector

The inspector (`app/database/inspector.py`) extracts schema information. You'll need a version for your database:

```python
class PostgresInspector:
    def __init__(self, connection_params: dict):
        self.params = connection_params

    def get_column_stats(self, table_name: str, limit: int = 1000) -> Dict[str, Any]:
        """
        Analyze columns to find:
        - Data types
        - Sample values
        - Low-cardinality columns (categorical)
        """
        # PostgreSQL example
        query = f"SELECT * FROM {table_name} LIMIT {limit}"
        
        # Use psycopg2 RealDictCursor for column-aware results
        # Analyze each column:
        # - unique_count = df[col].nunique()
        # - is_categorical = unique_count < 50 and dtype == 'object'
        # - sample_values = df[col].dropna().unique()[:10]
```

### Step 3: Update Configuration

Add database credentials to your environment or a config file:

```bash
# .env
DB_TYPE=postgres
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mydatabase
DB_USER=myuser
DB_PASSWORD=secret
```

### Step 4: Swap the Adapter

In `app/database/sqlite.py` (or wherever db_adapter is instantiated):

```python
# Option 1: Environment-based switch
import os

if os.environ.get("DB_TYPE") == "postgres":
    from app.database.postgres import PostgresAdapter
    db_adapter = PostgresAdapter()
else:
    from app.database.sqlite import SQLiteAdapter
    db_adapter = SQLiteAdapter()
```

## Database-Specific Considerations

### PostgreSQL

**Key Differences:**
- Use `information_schema` for metadata instead of `sqlite_master`
- Type casting: `column::numeric` instead of `CAST(column AS REAL)`
- String replacement: `REPLACE()` works the same
- Limit: `LIMIT 100` is standard
- Date functions: `TO_CHAR(date, 'YYYY')` instead of `strftime('%Y', date)`

**Common Query Patterns:**
```sql
-- SQLite
SELECT CAST(REPLACE(salary, '$', '') AS REAL) FROM payroll

-- PostgreSQL  
SELECT (salary::text)::numeric FROM payroll
-- Or use regex
SELECT regexp_replace(salary, '[$,]', '', 'g')::numeric FROM payroll
```

### MySQL

**Key Differences:**
- Use `information_schema` for metadata
- Type casting: `CAST(column AS DECIMAL(10,2))` or `CONVERT(column, SIGNED)`
- String replacement: `REPLACE()` works the same
- Limit: `LIMIT 100` is standard
- Date functions: `DATE_FORMAT(date, '%Y')` instead of `strftime('%Y', date)`

**Common Query Patterns:**
```sql
-- SQLite
SELECT CAST(REPLACE(salary, '$', '') AS REAL) FROM payroll

-- MySQL
SELECT CAST(REPLACE(REPLACE(salary, '$', ''), ',', '') AS DECIMAL(10,2)) FROM payroll
```

### SQL Server

**Key Differences:**
- Use `information_schema` for metadata
- Type casting: `CAST(column AS DECIMAL(10,2))` or `CONVERT(DECIMAL(10,2), column)`
- String replacement: `REPLACE()` works the same
- Limit: `TOP 100` instead of `LIMIT` (or use OFFSET with FETCH)
- Date functions: `FORMAT(date, 'yyyy')` or `DATEPART(year, date)`

## Required Interface Methods

Your adapter MUST implement these methods from `DatabaseAdapter`:

| Method | Purpose |
|--------|---------|
| `execute_query(query)` | Run SQL, return `{"columns": [], "data": []}` or `{"error": "..."}` |
| `get_schema(table_name)` | Return table DDL or column definitions |
| `get_rich_context()` | Return full context string for all tables |

## Handling Money/Currency Fields

The current POC handles `$` symbols in salary fields. When migrating:

```python
def clean_currency(value):
    """Generic currency cleaning - use in your adapter or let the LLM handle it"""
    if value is None:
        return None
    # Remove $, commas, convert to float
    return float(str(value).replace('$', '').replace(',', ''))
```

However, it's better to let the LLM generate correct SQL for your specific database:

**In your adapter's context generation:**
```python
def get_rich_context(self) -> str:
    # Detect money/currency columns
    money_columns = self._find_money_columns(tables)
    
    context = "### Database Notes\n"
    if money_columns:
        context += "- The following columns contain currency values and need casting:\n"
        for col in money_columns:
            context += f"  - {col}: Use CAST({col}::numeric) or CONVERT in SQL\n"
```

## Testing Your Migration

### 1. Unit Test the Adapter

```python
def test_postgres_adapter():
    adapter = PostgresAdapter()
    
    # Test connection
    result = adapter.execute_query("SELECT 1 as test")
    assert result["data"][0]["test"] == 1
    
    # Test schema
    schema = adapter.get_schema("users")
    assert "id" in schema.lower()
    
    # Test context
    ctx = adapter.get_rich_context()
    assert len(ctx) > 0
```

### 2. Run Existing Evals

```bash
python run_evals.py
```

If your new database has different table names or schemas, update the test cases in `tests/golden_sql/` to match.

### 3. Test Error Handling

```python
def test_write_blocked():
    adapter = PostgresAdapter()
    result = adapter.execute_query("DROP TABLE users")
    assert "error" in result
    assert "Write operations" in result["error"]
```

## Common Pitfalls

1.  **Case Sensitivity**: PostgreSQL column names can be case-sensitive. Use double quotes: `SELECT "UserName" FROM users`
2.  **Connection Pooling**: For production, use a connection pool (e.g., `psycopg2.pool`) instead of creating new connections per request.
3.  **Timeout Handling**: Set appropriate timeouts for long-running queries.
4.  **SSL**: Ensure SSL connections work in production environments.
5.  **Schema Qualification**: Always consider `schema.table` (e.g., `public.users`) in PostgreSQL.

## Summary

To migrate to a new database:

1.  Create `app/database/yourdb.py` implementing `DatabaseAdapter`
2.  Implement `execute_query`, `get_schema`, and `get_rich_context`
3.  Update inspector to use your database's metadata tables
4.  Swap the adapter in your configuration
5.  Update golden SQL tests if syntax differs
6.  Test thoroughly

The rest of the application (Agent, Memory, API, UI) requires **zero changes**.
