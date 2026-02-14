import re
import json
import asyncio
import time
from typing import List, Dict, Any, Optional
from app.database.sqlite import db_adapter
from app.utils.llm import query_llm_sync
from app.memory.sql_memory import sql_memory
from app.memory.query_history import query_history
from app.memory.conversation_store import conversation_store

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


def get_conversation_history(conversation_id: str) -> List[Dict[str, str]]:
    """Get conversation history for a specific conversation"""
    return conversation_store.get_conversation(conversation_id)


def list_conversations() -> List[Dict[str, Any]]:
    """List all active conversations with metadata"""
    return conversation_store.list_conversations()


def add_to_conversation(conversation_id: str, role: str, content: str):
    """Add a message to conversation history"""
    messages = conversation_store.get_conversation(conversation_id)
    
    # Keep last 10 messages context window logic if desired, 
    # but for storage we might want to keep everything and only slice on retrieval?
    # The original requirement was "Maintains last 10 messages" context.
    # Let's append to storage, but `process_question_stream` handles context window.
    
    messages.append({
        "role": role,
        "content": content
    })
    
    # Optional: Prune if file gets too large? 
    # For now, let's keep full history in file, but maybe limit if needed later.
    
    conversation_store.save_conversation(conversation_id, messages)


def clear_conversation(conversation_id: str):
    """Clear conversation history"""
    conversation_store.clear_conversation(conversation_id)


def extract_tables_from_sql(sql: str) -> List[str]:
    """Extract table names from SQL"""
    # Simple extraction - looks for 'FROM table_name' and 'JOIN table_name'
    tables = set()
    sql_lower = sql.lower()
    
    # Match FROM clause
    from_matches = re.findall(r'from\s+(\w+)', sql_lower)
    tables.update(from_matches)
    
    # Match JOIN clause
    join_matches = re.findall(r'join\s+(\w+)', sql_lower)
    tables.update(join_matches)
    
    return list(tables)


def validate_sql_safety(sql: str) -> tuple[bool, str]:
    """
    Validate SQL for common issues before execution.
    Returns (is_valid, warning_message)
    """
    warnings = []
    sql_lower = sql.lower()
    
    # Check for many-to-many join risk (multiple joins without proper aggregation)
    join_count = len(re.findall(r'\bjoin\b', sql_lower))
    has_group_by = 'group by' in sql_lower
    has_aggregation = any(agg in sql_lower for agg in ['sum(', 'count(', 'avg(', 'min(', 'max('])
    
    if join_count >= 2 and not has_group_by and not has_aggregation:
        warnings.append("Multiple joins detected without GROUP BY - may cause duplicate rows")
    
    # Check for NULL handling in aggregations
    if has_aggregation and 'coalesce(' not in sql_lower and 'ifnull(' not in sql_lower:
        warnings.append("Aggregations may need NULL handling with COALESCE()")
    
    # Check for LIMIT
    if 'limit' not in sql_lower:
        warnings.append("Query may benefit from LIMIT clause")
    
    is_valid = len(warnings) == 0
    return is_valid, "; ".join(warnings) if warnings else ""


async def process_question_stream(
    question: str, 
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None
):
    """
    Enhanced Agent with Memory, Multi-turn Conversations, and Validation.
    
    Args:
        question: The user's natural language question
        conversation_id: Optional ID for multi-turn conversation
        user_id: Optional user ID for personalized memories
    """
    start_time = time.time()
    
    # Get conversation history if available
    conversation_history = []
    if conversation_id:
        full_history = get_conversation_history(conversation_id)
        # Use last 10 messages for context window
        conversation_history = full_history[-10:] if full_history else []
    
    # Build context with memory systems
    base_context = db_adapter.get_rich_context()
    
    # Get learned patterns from query history
    history_context = query_history.get_context_for_question(question)
    
    # Get relevant memories (corrections)
    memory_context = sql_memory.get_memory_context_string(
        question=question,
        user_id=user_id
    )
    
    # Combine all context
    full_context = f"""
{base_context}

{history_context}

{memory_context}
""".strip()
    
    # --- Phase 1: Generate SQL ---
    system_prompt = f"""
You are an expert Data Agent. 
Your goal is to answer user questions by querying a SQLite database.

### Database Context
{full_context}

### Rules
1. Output ONLY standard SQLite SQL inside ```sql``` code blocks.
2. Do not use Markdown formatting outside the code block for the SQL.
3. If the question cannot be answered with the data, say "I cannot answer this with the available data."
4. Use 'LIKE' for loose string matching (e.g. agency names).
5. Always LIMIT results to 100 unless specified otherwise.
6. IMPORTANT: Check the 'Column Insights' section above.
   - Use the 'Possible values' list for exact matches in WHERE clauses.
   - Use 'Sample values' to understand data formats (dates, currency).
   - Salary/Money fields are TEXT with '$'. You MUST use `CAST(REPLACE(col, '$', '') AS REAL)` for calculations.
7. If a question is ambiguous (e.g., missing date range), apply sensible defaults and mention them.
8. When referring to previous context in follow-up questions, use clarifying language like "Based on the previous query..."

### Conversation Handling
- This may be a follow-up question. Consider previous context if provided.
- If the user refers to "that", "it", "the previous result", etc., clarify what they mean.
"""
    
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add conversation history if available
    if conversation_history:
        messages.extend(conversation_history)
    
    # Add current question
    messages.append({"role": "user", "content": question})
    
    # Yield planning step start
    yield json.dumps({"type": "status", "message": "Analyzing schema & planning..."})
    
    reasoning, content = query_llm_sync(messages)
    
    yield json.dumps({
        "type": "step", 
        "step": "plan", 
        "reasoning": reasoning, 
        "content": content
    })
    
    sql = extract_code_block(content, "sql") or ""
    if not sql:
        # Check if LLM is asking for clarification
        if any(phrase in content.lower() for phrase in ['clarify', 'specify', 'which', 'what do you mean']):
            yield json.dumps({
                "type": "final",
                "final_answer": content,
                "data": None,
                "chart": None,
                "clarification_needed": True
            })
        else:
            yield json.dumps({
                "type": "final",
                "final_answer": content,
                "data": None,
                "chart": None
            })
        return
    
    # Validate SQL before execution
    is_valid, warning = validate_sql_safety(sql)
    if not is_valid:
        yield json.dumps({
            "type": "step",
            "step": "warning",
            "message": f"SQL Validation: {warning}"
        })
    
    # --- Phase 2: Execution Loop ---
    query_result = None
    tables_used = []
    exec_time = 0
    
    for attempt in range(MAX_RETRIES):
        yield json.dumps({"type": "status", "message": f"Executing SQL (Attempt {attempt+1})..."})
        yield json.dumps({"type": "step", "step": "execution", "sql": sql, "attempt": attempt + 1})
        
        exec_start = time.time()
        result = db_adapter.execute_query(sql)
        exec_time = int((time.time() - exec_start) * 1000)
        
        if "error" in result:
            error_msg = result["error"]
            yield json.dumps({"type": "step", "step": "error", "message": error_msg})
            
            # Retry prompt with memory of error
            retry_msg = f"""The query failed with error: {error_msg}. 

Please correct the SQL. Consider:
- Checking table and column names
- Ensuring proper syntax for SQLite
- Handling NULL values appropriately
- Ver JOIN conditions

Output ONLY the fixed SQL inside ```sql```."""
            
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
            tables_used = extract_tables_from_sql(sql)
            yield json.dumps({"type": "step", "step": "success", "rows_returned": len(result["data"])})
            break
            
    if not query_result or "error" in query_result:
        final_answer = "I failed to execute a valid query after multiple attempts."
        
        # Log failed query
        query_history.log_query(
            question=question,
            sql=sql if sql else "",
            tables=tables_used,
            execution_time_ms=int((time.time() - start_time) * 1000),
            success=False,
            row_count=0,
            user_id=user_id
        )
        
        yield json.dumps({
            "type": "final",
            "final_answer": final_answer,
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
2. Explain any assumptions made (e.g., date ranges, filters).
3. Determine if this data should be visualized.
4. If yes, output a JSON object inside ```json``` compatible with Chart.js:
   {{ "chart_type": "bar", "x_axis": "column_name", "y_axis": "column_name", "title": "Chart Title" }}
   - If no chart is suitable, output {{ "chart_type": null }}
"""
    
    messages.append({"role": "assistant", "content": f"I executed: ```sql\n{sql}\n```"})
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
    
    # --- Phase 4: Logging & Memory ---
    total_time = int((time.time() - start_time) * 1000)
    exec_time = exec_time if 'exec_time' in locals() else 0
    
    # Log successful query
    query_history.log_query(
        question=question,
        sql=sql if sql else "",
        tables=tables_used,
        execution_time_ms=total_time,
        success=True,
        row_count=full_data_len,
        user_id=user_id
    )
    
    # Update conversation history
    if conversation_id:
        add_to_conversation(conversation_id, "user", question)
        add_to_conversation(conversation_id, "assistant", f"SQL: {sql}\n\nResult: {final_text}")
    
    yield json.dumps({
        "type": "final",
        "final_answer": final_text,
        "data": query_result,
        "chart": chart_def,
        "query_info": {
            "sql": sql if sql else "",
            "tables_used": tables_used,
            "execution_time_ms": exec_time,
            "rows_returned": full_data_len
        }
    })


async def save_memory_from_feedback(
    question: str,
    sql: str,
    correction: str,
    tables: List[str],
    user_id: Optional[str] = None,
    scope: str = "global"
):
    """
    Save a correction as memory based on user feedback.
    This can be called when user indicates the SQL was incorrect.
    """
    # Extract columns mentioned in correction
    # This is simplified - in production, use NLP to extract column references
    columns = []
    
    memory = sql_memory.add_memory(
        pattern=question,
        correction=correction,
        applies_to_tables=tables,
        applies_to_columns=columns,
        memory_type="correction",
        scope=scope,
        user_id=user_id
    )
    
    return memory
