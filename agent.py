import re
import json
import asyncio
from database import get_schema_info, execute_query
from llm import query_llm_sync

MAX_RETRIES = 3

def extract_code_block(text, lang="sql"):
    pattern = rf"```{lang}\s*(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None

def extract_json_block(text):
    pattern = r"```json\s*(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return text[start:end+1]
    return None

async def process_question_stream(question: str):
    """
    Generator that yields JSON strings for Server-Sent Events (SSE).
    Events:
    - {"type": "step", "step": "...", "content": "...", "reasoning": "..."}
    - {"type": "final", "final_answer": "...", "data": ..., "chart": ...}
    """
    schema = get_schema_info()
    
    # --- Phase 1: Generate SQL ---
    system_prompt = f"""
    You are an expert Data Agent. 
    Your goal is to answer user questions by querying a SQLite database.
    
    {schema}
    
    Rules:
    1. Output ONLY standard SQLite SQL inside ```sql``` code blocks.
    2. Do not use Markdown formatting outside the code block for the SQL.
    3. If the question cannot be answered with the data, say "I cannot answer this with the available data."
    4. Use 'LIKE' for loose string matching (e.g. agency names).
    5. Always LIMIT results to 100 unless specified otherwise.
    """
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question}
    ]
    
    # Yield planning step start
    yield json.dumps({"type": "status", "message": "Planning query..."})
    
    # For now, we still use sync LLM call for simplicity in logic, but yield the result immediately
    # (To do true token streaming we'd need to refactor llm.py heavily)
    reasoning, content = query_llm_sync(messages)
    
    yield json.dumps({
        "type": "step", 
        "step": "plan", 
        "reasoning": reasoning, 
        "content": content
    })
    
    sql = extract_code_block(content, "sql")
    if not sql:
        yield json.dumps({
            "type": "final",
            "final_answer": content,
            "data": None,
            "chart": None
        })
        return
    
    # --- Phase 2: Execution Loop ---
    query_result = None
    
    for attempt in range(MAX_RETRIES):
        yield json.dumps({"type": "status", "message": f"Executing SQL (Attempt {attempt+1})..."})
        yield json.dumps({"type": "step", "step": "execution", "sql": sql, "attempt": attempt + 1})
        
        result = execute_query(sql)
        
        if "error" in result:
            error_msg = result["error"]
            yield json.dumps({"type": "step", "step": "error", "message": error_msg})
            
            # Retry prompt
            retry_msg = f"The query failed with error: {error_msg}. Please correct the SQL. Output ONLY the fixed SQL inside ```sql```."
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": retry_msg})
            
            yield json.dumps({"type": "status", "message": "Refining SQL..."})
            reasoning, content = query_llm_sync(messages)
            yield json.dumps({"type": "step", "step": "retry_plan", "reasoning": reasoning, "content": content})
            
            sql = extract_code_block(content, "sql")
            if not sql:
                break 
        else:
            query_result = result
            yield json.dumps({"type": "step", "step": "success", "rows_returned": len(result["data"])})
            break
            
    if not query_result or "error" in query_result:
        yield json.dumps({
            "type": "final",
            "final_answer": "I failed to execute a valid query after multiple attempts.",
            "data": None,
            "chart": None
        })
        return

    # --- Phase 3: Analysis & Visualization ---
    yield json.dumps({"type": "status", "message": "Analyzing results..."})
    
    data_preview = query_result["data"][:5]
    columns = query_result["columns"]
    full_data_len = len(query_result["data"])
    
    analysis_prompt = f"""
    The query executed successfully.
    Rows returned: {full_data_len}
    Columns: {columns}
    Sample Data: {data_preview}
    
    Task:
    1. Provide a concise answer to the original question based on this data.
    2. Determine if this data should be visualized.
    3. If yes, output a JSON object inside ```json``` compatible with Chart.js:
       {{ "chart_type": "bar", "x_axis": "column_name", "y_axis": "column_name", "title": "Chart Title" }}
       - If no chart is suitable, output {{ "chart_type": null }}
    """
    
    messages.append({"role": "user", "content": analysis_prompt})
    reasoning, content = query_llm_sync(messages)
    yield json.dumps({"type": "step", "step": "analysis", "reasoning": reasoning, "content": content})
    
    chart_config = extract_json_block(content)
    chart_def = None
    if chart_config:
        try:
            chart_meta = json.loads(chart_config)
            if chart_meta.get("chart_type"):
                x_col = chart_meta.get("x_axis")
                y_col = chart_meta.get("y_axis")
                
                if x_col in columns and y_col in columns:
                    labels = [row[x_col] for row in query_result["data"]]
                    values = [row[y_col] for row in query_result["data"]]
                    
                    chart_def = {
                        "type": chart_meta["chart_type"],
                        "data": {
                            "labels": labels,
                            "datasets": [{
                                "label": chart_meta.get("title", y_col),
                                "data": values,
                                "backgroundColor": "rgba(75, 192, 192, 0.2)",
                                "borderColor": "rgba(75, 192, 192, 1)",
                                "borderWidth": 1
                            }]
                        },
                        "options": {
                            "responsive": True,
                            "scales": {
                                "y": {"beginAtZero": True}
                            }
                        }
                    }
        except:
            pass

    final_text = re.sub(r"```json.*?```", "", content, flags=re.DOTALL).strip()
    
    yield json.dumps({
        "type": "final",
        "final_answer": final_text,
        "data": query_result,
        "chart": chart_def
    })

