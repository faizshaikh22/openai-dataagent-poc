from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse
from app.agent.core import process_question_stream

app = FastAPI()

# Mount static files (relative to project root)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates (relative to project root)
templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/chat_stream")
async def chat_stream(message: str):
    return EventSourceResponse(process_question_stream(message))
