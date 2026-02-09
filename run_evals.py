import sqlite3
import re
from agent import DataAgent
from tools import DB_FILE

def get_generated_sql(steps):
    """Extracts the last SQL query from the agent's steps."""
    for step in reversed(steps):
        match = re.search(r"Action: run_sql\nAction Input:\s*(.+)", step, re.DOTALL)
        if match:
            return match.group(1).strip()
    return None

def execute_sql(query):
    """Executes SQL and returns the result set (list of tuples)."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        conn.close()
        return results
    except Exception as e:
        return str(e)

def run_evals():
    agent = DataAgent()

    test_cases = [
        {
            "id": "TC-01",
            "question": "What is the highest base salary?",
            "golden_sql": "SELECT MAX(base_salary) FROM payroll"
        },
        {
            "id": "TC-02",
            "question": "Count the number of agencies.",
            "golden_sql": "SELECT COUNT(DISTINCT agency_name) FROM payroll"
        },
        {
            "id": "TC-03",
            "question": "Show me the top 3 OT earners.",
            "golden_sql": "SELECT first_name, last_name, total_ot_paid FROM payroll ORDER BY total_ot_paid DESC LIMIT 3"
        }
    ]

    print(f"{'ID':<10} | {'Status':<10} | {'Details'}")
    print("-" * 50)

    passed = 0

    for case in test_cases:
        print(f"Running {case['id']}...", end="\r")

        # Run agent
        try:
            answer, steps = agent.run(case["question"])
        except Exception as e:
            print(f"{case['id']:<10} | ERROR      | Agent failed: {e}")
            continue

        # Extract SQL
        gen_sql = get_generated_sql(steps)

        if not gen_sql:
            print(f"{case['id']:<10} | FAIL       | No SQL generated")
            continue

        # Compare Results (relaxed check: just verify non-empty and potentially matching first row if scalar)
        golden_res = execute_sql(case["golden_sql"])
        gen_res = execute_sql(gen_sql)

        # Exact match is hard for complex queries, so we check if result is same
        # If result is list of tuples, we compare contents.
        if str(golden_res) == str(gen_res):
            print(f"{case['id']:<10} | PASS       | Results match")
            passed += 1
        else:
            # Maybe the agent selected extra columns?
            # For POC, let's just log it.
            print(f"{case['id']:<10} | FAIL       | Results differ")
            print(f"  Golden: {golden_res}")
            print(f"  Gen:    {gen_res}")
            print(f"  SQL:    {gen_sql}")

    print("-" * 50)
    print(f"Passed {passed}/{len(test_cases)} tests.")

if __name__ == "__main__":
    run_evals()
