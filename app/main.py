from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from app.api.models import ChatRequest
from app.core.agent import get_agent
from app.core.knowledge import ingest_pdfs
import json
import os

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    if os.path.exists("static/index.html"):
        return FileResponse('static/index.html')
    return {"message": "Frontend not found. Please add static/index.html"}

@app.post("/ingest")
async def ingest_endpoint():
    try:
        result = ingest_pdfs()
        return {"status": "success", "details": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Streaming chat endpoint.
    """
    agent = get_agent(session_id=request.session_id)

    async def generate():
        # Agno agents return a generator for streaming
        # agent.run(stream=True) yields ChatResponse objects or strings depending on configuration
        # We need to yield text chunks

        # Note: Agno's `run(stream=True)` returns an Iterator[RunResponse]
        # We need to iterate and extract content.

        try:
            # We use `run` with stream=True.
            response_generator = agent.run(request.message, stream=True)

            for chunk in response_generator:
                # Chunk is usually a RunResponse object in Agno 2.x
                # Or if markdown=True, it might yield strings?
                # Let's inspect typical behavior. Agno 2.x `run(stream=True)` yields RunResponse.
                # Actually, `agent.print_response` handles printing.
                # `agent.run(stream=True)` yields `RunResponse` where `content` is the delta?
                # No, `RunResponse` is the full object.
                # Let's verify Agno streaming behavior.

                # Assuming chunk.content contains the delta text.
                if hasattr(chunk, "content") and chunk.content:
                     yield chunk.content
                elif isinstance(chunk, str):
                     yield chunk

        except Exception as e:
            yield f"Error: {str(e)}"

    return StreamingResponse(generate(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
