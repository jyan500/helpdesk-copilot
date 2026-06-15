import asyncio
from dotenv import load_dotenv

# Load .env into os.environ BEFORE anything reads it (genai.Client() picks up
# GEMINI_API_KEY here). FastAPI/uvicorn does not auto-load .env.
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.sse import EventSourceResponse
from utils.client import LLMClient

app = FastAPI()
llm = LLMClient()

# Enable CORS for next.js development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SSE Format strictly requires "data: <payload>\n\n"
# always separate consecutive messages with double newlines
# when using EventSourceResponse, this automates this for you
@app.get("/api/chat", response_class=EventSourceResponse)
async def chat_endpoint(message: str):
	async for delta in llm.stream_response(message):
		yield {"delta": delta}
	yield {"done": True}
