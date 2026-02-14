from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.agent.core import process_question_stream, save_memory_from_feedback, clear_conversation
from app.memory.sql_memory import sql_memory
from app.memory.query_history import query_history

app = FastAPI()

# Mount static files (relative to project root)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates (relative to project root)
templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/chat_stream")
async def chat_stream(message: str, conversation_id: str = None, user_id: str = None):
    """
    Stream chat responses with support for multi-turn conversations.
    
    Args:
        message: The user's question
        conversation_id: Optional ID to maintain conversation context
        user_id: Optional user ID for personalized memories
    """
    return EventSourceResponse(process_question_stream(message, conversation_id, user_id))


# --- Memory Management Endpoints ---

class MemoryCreateRequest(BaseModel):
    pattern: str
    correction: str
    applies_to_tables: List[str] = []
    applies_to_columns: List[str] = []
    memory_type: str = "general"
    scope: str = "global"
    user_id: Optional[str] = None


@app.post("/api/memories")
async def create_memory(request: MemoryCreateRequest):
    """Create a new SQL memory/correction"""
    try:
        memory = sql_memory.add_memory(
            pattern=request.pattern,
            correction=request.correction,
            applies_to_tables=request.applies_to_tables,
            applies_to_columns=request.applies_to_columns,
            memory_type=request.memory_type,
            scope=request.scope,
            user_id=request.user_id
        )
        return {"success": True, "memory": memory.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/memories")
async def list_memories(scope: str = "global", user_id: str = None):
    """List all memories"""
    memories = sql_memory.list_all_memories(scope=scope, user_id=user_id)
    return {"memories": [m.to_dict() for m in memories]}


@app.delete("/api/memories/{memory_id}")
async def delete_memory(memory_id: str, user_id: str = None):
    """Delete a memory by ID"""
    success = sql_memory.delete_memory(memory_id, user_id=user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True}


class FeedbackRequest(BaseModel):
    question: str
    sql: str
    correction: str
    tables: List[str]
    user_id: Optional[str] = None
    scope: str = "global"


@app.post("/api/feedback")
async def submit_feedback(request: FeedbackRequest):
    """Submit feedback to create a memory from a correction"""
    from app.agent.core import save_memory_from_feedback
    
    memory = await save_memory_from_feedback(
        question=request.question,
        sql=request.sql,
        correction=request.correction,
        tables=request.tables,
        user_id=request.user_id,
        scope=request.scope
    )
    return {"success": True, "memory": memory.to_dict()}


# --- Query History Endpoints ---

@app.get("/api/query-history/popular")
async def get_popular_queries(table: str = None, limit: int = 5):
    """Get popular query patterns"""
    popular = query_history.get_popular_queries(table=table, limit=limit)
    return {"queries": popular}


@app.get("/api/query-history/join-suggestions")
async def get_join_suggestions(tables: str):
    """Get join suggestions for tables (comma-separated)"""
    table_list = [t.strip() for t in tables.split(",")]
    suggestions = query_history.get_join_suggestions(table_list)
    return {"suggestions": suggestions}


# --- Conversation Management ---

@app.post("/api/conversations/{conversation_id}/clear")
async def clear_conversation_endpoint(conversation_id: str):
    """Clear conversation history"""
    clear_conversation(conversation_id)
    return {"success": True, "message": f"Conversation {conversation_id} cleared"}


@app.get("/api/conversations")
async def get_conversations():
    """List active conversations"""
    from app.agent.core import list_conversations
    return {"conversations": list_conversations()}


@app.get("/api/conversations/{conversation_id}")
async def get_conversation_history_endpoint(conversation_id: str):
    """Get history for a specific conversation"""
    from app.agent.core import get_conversation_history
    history = get_conversation_history(conversation_id)
    return {"history": history}


# --- Workflow Endpoints ---

@app.get("/api/workflows")
async def list_workflows(category: str = None):
    """List available workflow templates"""
    from app.workflows import workflow_engine
    workflows = workflow_engine.list_workflows(category=category)
    return {"workflows": workflows}


class WorkflowExecuteRequest(BaseModel):
    workflow_name: str
    parameters: Dict[str, Any]
    user_id: Optional[str] = None


@app.post("/api/workflows/execute")
async def execute_workflow(request: WorkflowExecuteRequest):
    """Execute a workflow template with parameters"""
    from app.workflows import workflow_engine
    from app.database.sqlite import db_adapter
    
    try:
        results = await workflow_engine.execute_workflow(
            workflow_name=request.workflow_name,
            params=request.parameters,
            db_adapter=db_adapter,
            user_id=request.user_id
        )
        return {"success": True, "results": results}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
