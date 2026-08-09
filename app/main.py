from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

from app.agents.orchestrator import RoadMateOrchestrator
from app.integrations.gmail import GmailClient, GmailConfigurationError
from app.integrations.local_files import LocalDocumentParser, UnsupportedDocumentError
from app.integrations.routes import RoutesClient
from app.models import ChatRequest, ChatResponse, RagQuery, RouteRequest
from app.rag.store import LocalRagStore

app = FastAPI(title="Road Friend", version="0.3.0")
rag = LocalRagStore()
orchestrator = RoadMateOrchestrator(rag=rag)
routes = RoutesClient()
gmail = GmailClient()
file_parser = LocalDocumentParser()

CHAT_COUNT = Counter("roadfriend_chat_total", "Chat requests", ["intent"])
CHAT_LATENCY = Histogram("roadfriend_chat_latency_seconds", "Chat request latency")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "service": "road-friend"}


@app.get("/v1/capabilities")
def capabilities() -> dict:
    return {
        "voice_text": True,
        "live_location": True,
        "places_routes": True,
        "google_grounded_questions": True,
        "documents": sorted(LocalDocumentParser.SUPPORTED),
        "gmail_oauth": True,
        "spotify": True,
        "macos_messages_optional": True,
        "permission_model": "private reads require permission; external sends require one-time confirmation",
    }


@app.post("/v1/chat", response_model=ChatResponse)
@CHAT_LATENCY.time()
async def chat(req: ChatRequest) -> ChatResponse:
    response = await orchestrator.handle(req)
    CHAT_COUNT.labels(response.intent).inc()
    return response


@app.post("/v1/route")
async def route(req: RouteRequest) -> dict:
    return await routes.route(req.origin, req.destination, req.travel_mode)


@app.post("/v1/files/ingest")
async def ingest_file(session_id: str, file: UploadFile = File(...)) -> dict:
    data = await file.read()
    filename = file.filename or "document.txt"
    try:
        text = file_parser.parse(filename, data)
    except UnsupportedDocumentError as exc:
        return {"ok": False, "error": str(exc)}
    if not text.strip():
        return {"ok": False, "error": "I could not extract readable text from that file."}
    chunks = rag.ingest_text(text, filename)
    orchestrator.register_document(session_id, filename)
    return {
        "ok": True,
        "filename": filename,
        "characters": len(text),
        "chunks": chunks,
        "message": f"I can now answer questions about {filename}.",
    }


@app.post("/v1/rag/ingest")
async def rag_ingest(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    filename = file.filename or "upload.txt"
    text = file_parser.parse(filename, data)
    chunks = rag.ingest_text(text, filename)
    return {"chunks": chunks, "source": filename}


@app.post("/v1/rag/query")
def rag_query(req: RagQuery) -> dict:
    return {"question": req.question, "evidence": rag.query(req.question, req.top_k)}


@app.get("/v1/integrations/gmail/status")
def gmail_status() -> dict:
    return {
        "connected": gmail.connected(),
        "credentials_file_present": gmail.credentials_exist(),
    }


@app.post("/v1/integrations/gmail/connect")
async def gmail_connect() -> dict:
    try:
        return {"ok": True, **(await gmail.connect())}
    except GmailConfigurationError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": f"Gmail connection failed: {exc}"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/", response_class=HTMLResponse)
def web_ui() -> HTMLResponse:
    return HTMLResponse(Path("app/web/index.html").read_text(encoding="utf-8"))


@app.websocket("/ws/assistant")
async def ws_assistant(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            payload = json.loads(await ws.receive_text())
            req = ChatRequest.model_validate(payload)
            response = await orchestrator.handle(req)
            CHAT_COUNT.labels(response.intent).inc()
            await ws.send_json(response.model_dump())
    except WebSocketDisconnect:
        return
