from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import os
import json
from agent import DataAgent

app = FastAPI()

# Data Models
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"

class ChatResponse(BaseModel):
    reply: str
    thoughts: List[str]

# Global state
agents = {}

# API Endpoints
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        session_id = request.session_id
        if session_id not in agents:
            agents[session_id] = DataAgent()

        agent = agents[session_id]
        reply, thoughts = agent.run(request.message)

        return ChatResponse(reply=reply, thoughts=thoughts)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/reset")
async def reset_endpoint():
    MEMORY_FILE = "memory.json"
    with open(MEMORY_FILE, "w") as f:
        json.dump([], f)
    agents.clear()
    return {"status": "memory and agents reset"}

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse('static/index.html')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
