from database import get_schema_info, execute_query

print("--- SCHEMA ---")
print(get_schema_info()[:500] + "...")
print("\n--- QUERY TEST ---")
res = execute_query("SELECT * FROM payroll LIMIT 2")
print(res)
