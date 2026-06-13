import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse 

app = FastAPI()

# Enable CORS for next.js development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def event_generator():
	""" Generates continuous data events """
	count = 0
	while True:
		await asyncio.sleep(1)
		count += 1

		# SSE Format strictly requires "data: <payload>\n\n"
		# always separate consecutive messages with double newlines
		yield f"data: {{'message': 'Hello from FASTAPI', 'count': {count}}}\n\n"

@app.get("/api/sse")
async def sse_endpoint():
	return StreamingResponse(event_generator(), media_type="text/event-stream")
