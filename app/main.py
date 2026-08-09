from __future__ import annotations
import json
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
from app.agents.orchestrator import RoadMateOrchestrator
from app.models import ChatRequest, ChatResponse, RouteRequest, RagQuery
from app.integrations.routes import RoutesClient
from app.rag.store import LocalRagStore

app = FastAPI(title="RoadMate AI", version="0.1.0")
orchestrator = RoadMateOrchestrator()
routes = RoutesClient()
rag = LocalRagStore()
CHAT_COUNT = Counter("roadmate_chat_total", "Chat requests", ["intent"])
CHAT_LATENCY = Histogram("roadmate_chat_latency_seconds", "Chat request latency")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "service": "roadmate-ai"}


@app.post("/v1/chat", response_model=ChatResponse)
@CHAT_LATENCY.time()
async def chat(req: ChatRequest) -> ChatResponse:
    response = await orchestrator.handle(req)
    CHAT_COUNT.labels(response.intent).inc()
    return response


@app.post("/v1/route")
async def route(req: RouteRequest) -> dict:
    return await routes.route(req.origin, req.destination, req.travel_mode)


@app.post("/v1/rag/ingest")
async def rag_ingest(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "upload").suffix.lower()
    data = await file.read()
    tmp = Path("artifacts") / (file.filename or "upload.txt")
    tmp.parent.mkdir(exist_ok=True)
    tmp.write_bytes(data)
    if suffix == ".pdf":
        chunks = rag.ingest_pdf(str(tmp))
    else:
        chunks = rag.ingest_text(data.decode("utf-8", errors="ignore"), file.filename or "upload")
    return {"chunks": chunks, "source": file.filename}


@app.post("/v1/rag/query")
def rag_query(req: RagQuery) -> dict:
    return {"question": req.question, "evidence": rag.query(req.question, req.top_k)}


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
            await ws.send_json(response.model_dump())
    except WebSocketDisconnect:
        return
