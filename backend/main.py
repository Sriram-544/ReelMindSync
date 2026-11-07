"""
main.py — ReelMind FastAPI Server

Serves the website (marketing page + app UI) and all API endpoints.
Run with:  python main.py
Then open: http://localhost:8000
"""

import asyncio
import json
import os
import sys
import threading
import traceback
import queue
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
WEBSITE_DIR = BASE_DIR.parent / "website"
DATA_DIR    = BASE_DIR / "data"
REELS_DIR   = DATA_DIR / "reels"
PROCESSED_DIR = DATA_DIR / "processed"
INDEX_DIR   = DATA_DIR / "reel_index"
THUMBS_DIR  = DATA_DIR / "thumbs"
GENERATED_DIR = DATA_DIR / "generated"

for d in [REELS_DIR, PROCESSED_DIR, INDEX_DIR, THUMBS_DIR, GENERATED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Pipeline state (shared between request thread + background thread) ─────────
_lock = threading.Lock()
_pipeline_queue = queue.Queue()

_state: dict = {
    "status":           "idle",   # idle | running | done | error
    "phase":            0,        # 1-3
    "phase_name":       "",
    "progress":         0,
    "total":            0,
    "message":          "",
    "error":            None,
    "reels_downloaded": 0,
    "reels_processed":  0,
    "reels_indexed":    0,
}


def _update(**kwargs):
    with _lock:
        _state.update(kwargs)


def _snapshot() -> dict:
    with _lock:
        return dict(_state)


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="ReelMind", version="1.0.0", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request / Response models ──────────────────────────────────────────────────
class ExtensionStartRequest(BaseModel):
    reels: list[dict]

class ChatRequest(BaseModel):
    question: str

class ChatSingleRequest(BaseModel):
    shortcode: str
    question: str

class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""
    num_steps: int = 25
    height: int = 512
    width: int = 512
    num_frames: int = 16


# ── Page routes ────────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def index_page():
    return FileResponse(WEBSITE_DIR / "index.html")


@app.get("/app", include_in_schema=False)
async def app_page():
    return FileResponse(WEBSITE_DIR / "app.html")


# ── Thumbnail serving ──────────────────────────────────────────────────────────
@app.get("/thumbs/{filename}", include_in_schema=False)
async def serve_thumb(filename: str):
    path = THUMBS_DIR / filename
    if path.exists():
        return FileResponse(path)
    raise HTTPException(404, "Thumbnail not found")


# ── Reel Video serving ─────────────────────────────────────────────────────────
@app.get("/reels/{filename}", include_in_schema=False)
async def serve_reel(filename: str):
    path = REELS_DIR / filename
    if path.exists():
        return FileResponse(path)
    raise HTTPException(404, "Reel not found")


# ── Static asset catch-all (CSS, JS, fonts, images) ───────────────────────────


# ── API: Health ────────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    """Returns server health + Ollama availability + indexed reel count."""
    import httpx

    ollama_ok = False
    ollama_model = None
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get("http://localhost:11434/api/tags")
            if r.status_code == 200:
                ollama_ok = True
                models = r.json().get("models", [])
                # Prefer qwen2.5:7b then llama3.2 then any available model
                names = [m["name"] for m in models]
                ollama_model = next(
                    (n for n in names if "qwen2.5" in n),
                    next((n for n in names if "llama3.2" in n), names[0] if names else None),
                )
    except Exception:
        pass

    # Indexed reel count (don't fail if DB not initialized yet)
    reel_count = 0
    try:
        from indexer import ReelIndexer
        reel_count = ReelIndexer(str(INDEX_DIR)).count()
    except Exception:
        pass

    return {
        "status":           "ok",
        "ollama_available": ollama_ok,
        "ollama_model":     ollama_model,
        "reels_indexed":    reel_count,
        "pipeline_status":  _snapshot()["status"],
    }


# ── API: Pipeline ──────────────────────────────────────────────────────────────
@app.post("/api/pipeline/start_from_extension")
async def start_pipeline_extension(req: ExtensionStartRequest, background_tasks: BackgroundTasks):
    """Kicks off the full download → extract → index pipeline from extension data."""
    if not req.reels:
        raise HTTPException(400, "No reels provided.")

    # Deduplicate existing queue
    existing_shortcodes = {item.get("shortcode") for item in _pipeline_queue.queue}
    added_count = 0
    for reel in req.reels:
        if reel.get("shortcode") and reel.get("shortcode") not in existing_shortcodes:
            _pipeline_queue.put(reel)
            added_count += 1

    if added_count == 0:
        return {"success": True, "message": "All provided reels are already in the queue."}

    with _lock:
        if _state["status"] == "running":
            _state["total"] += added_count
            return {"success": True, "message": f"Appended {added_count} reels to the running pipeline."}
            
        _state.update({
            "status":           "running",
            "phase":            1,
            "phase_name":       "Preparing AI Models",
            "progress":         0,
            "total":            added_count,
            "message":          "Starting…",
            "error":            None,
            "reels_downloaded": 0,
            "reels_processed":  0,
            "reels_indexed":    0,
        })

    background_tasks.add_task(_run_pipeline_extension)
    return {"success": True, "message": f"Started pipeline with {added_count} reels."}


@app.get("/api/pipeline/status")
async def pipeline_status():
    """
    Server-Sent Events stream — sends state updates every 500ms.
    Closes automatically when the pipeline reaches done/error.
    """
    async def generator():
        last = None
        while True:
            snap = _snapshot()
            if snap != last:
                yield f"data: {json.dumps(snap)}\n\n"
                last = dict(snap)
            if snap["status"] in ("done", "error", "idle"):
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":   "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":      "keep-alive",
        },
    )


@app.get("/api/pipeline/state")
async def pipeline_state_snapshot():
    """Returns a single JSON snapshot of the current pipeline state."""
    return _snapshot()


# ── API: Reels ─────────────────────────────────────────────────────────────────
@app.get("/api/reels")
async def list_reels():
    """Lists all indexed reels with their metadata."""
    try:
        from indexer import ReelIndexer
        reels = ReelIndexer(str(INDEX_DIR)).list_reels()
        return {"reels": reels, "count": len(reels)}
    except Exception as e:
        return {"reels": [], "count": 0, "error": str(e)}

@app.get("/api/reels/{shortcode}")
async def get_reel(shortcode: str):
    """Fetches the full JSON data for a specific reel."""
    path = PROCESSED_DIR / f"{shortcode}.json"
    if not path.exists():
        raise HTTPException(404, "Reel data not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── API: Chat ──────────────────────────────────────────────────────────────────
@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Runs a RAG query against the indexed reel collection."""
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty.")

    try:
        from indexer import ReelIndexer
        if ReelIndexer(str(INDEX_DIR)).count() == 0:
            raise HTTPException(400, "No reels are indexed yet. Run the pipeline first.")
    except HTTPException:
        raise
    except Exception:
        pass

    try:
        from chat import ReelChat
        result = ReelChat(str(INDEX_DIR)).ask(req.question)
        return result
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, f"Chat error: {e}")

@app.post("/api/chat_single")
async def chat_single(req: ChatSingleRequest):
    """Answers a question using only the context of a single reel."""
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty.")
    
    path = PROCESSED_DIR / f"{req.shortcode}.json"
    if not path.exists():
        raise HTTPException(404, "Reel data not found")
        
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        content = data.get("content", "")
        if not content:
            raise HTTPException(400, "Reel has no transcript/content.")
            
        from chat import ReelChat
        result = ReelChat(str(INDEX_DIR)).ask_single_reel(content, req.question)
        return result
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, f"Chat error: {e}")


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Streams RAG chat tokens in real-time using SSE."""
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty.")

    def event_stream():
        try:
            from chat import ReelChat
            rc = ReelChat(str(INDEX_DIR))
            for item in rc.ask_stream(req.question):
                yield f"data: {json.dumps(item)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/chat_single/stream")
async def chat_single_stream(req: ChatSingleRequest):
    """Streams single-reel Q&A tokens in real-time using SSE."""
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty.")

    path = PROCESSED_DIR / f"{req.shortcode}.json"
    if not path.exists():
        raise HTTPException(404, "Reel data not found")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    content = data.get("content", "")
    if not content:
        raise HTTPException(400, "Reel has no transcript/content.")

    def event_stream():
        try:
            from chat import ReelChat
            rc = ReelChat(str(INDEX_DIR))
            for item in rc.ask_single_reel_stream(content, req.question):
                yield f"data: {json.dumps(item)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── API: Generate ──────────────────────────────────────────────────────────────

_generator = None

def _get_generator():
    global _generator
    if _generator is None:
        from generator import ReelGenerator
        _generator = ReelGenerator(str(GENERATED_DIR))
    return _generator


@app.post("/api/generate/image")
async def generate_image(req: GenerateRequest):
    """Generates an image from a text prompt using Stable Diffusion 1.5 (local GPU)."""
    if not req.prompt.strip():
        raise HTTPException(400, "Prompt cannot be empty.")
    try:
        gen = _get_generator()
        filename = gen.generate_image(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt,
            num_steps=req.num_steps,
            height=req.height,
            width=req.width,
        )
        return {"success": True, "filename": filename, "url": f"/generated/{filename}"}
    except Exception as e:
        raise HTTPException(500, f"Image generation failed: {e}")


@app.post("/api/generate/video")
async def generate_video(req: GenerateRequest):
    """Generates a short animated video (GIF) from a text prompt using AnimateDiff (local GPU)."""
    if not req.prompt.strip():
        raise HTTPException(400, "Prompt cannot be empty.")
    try:
        gen = _get_generator()
        filename = gen.generate_video(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt,
            num_steps=req.num_steps,
            num_frames=req.num_frames,
        )
        return {"success": True, "filename": filename, "url": f"/generated/{filename}"}
    except Exception as e:
        raise HTTPException(500, f"Video generation failed: {e}")


@app.get("/generated/{filename}", include_in_schema=False)
async def serve_generated(filename: str):
    """Serves generated image/video files."""
    path = GENERATED_DIR / filename
    if path.exists():
        return FileResponse(path)
    raise HTTPException(404, "Generated file not found")


# ── API: Cloud Generate ─────────────────────────────────────────────────────────

@app.post("/api/generate/cloud_image")
async def generate_cloud_image(req: GenerateRequest):
    """Returns a Pollinations.ai URL for free cloud image generation. Browser loads it directly."""
    if not req.prompt.strip():
        raise HTTPException(400, "Prompt cannot be empty.")
    try:
        from cloud_generator import build_url
        url = build_url(
            prompt=req.prompt,
            width=min(req.width, 1440),
            height=min(req.height, 1440),
        )
        return {"success": True, "url": url, "cloud": True}
    except Exception as e:
        raise HTTPException(500, f"Cloud URL build failed: {e}")


# ── Background pipeline ────────────────────────────────────────────────────────
def _run_pipeline_extension():
    """Executes the full pipeline per-reel so the UI can stream."""
    import time
    try:
        from downloader import ReelDownloader
        from reel_extractor import ReelExtractor
        from indexer import ReelIndexer
        import yt_dlp

        dl = ReelDownloader(str(REELS_DIR))
        extractor = ReelExtractor()
        indexer = ReelIndexer(str(INDEX_DIR))

        total = _state["total"]
        _update(phase=1, phase_name="Preparing Models", progress=0, message="Loading models...")
        
        # Pre-load models (force lazy loading to happen once)
        indexer._get_embed_model()
        indexer._get_collection()
        # Pre-load whisper model
        from reel_extractor import _get_whisper
        _get_whisper(extractor.whisper_model)

        _update(phase=2, phase_name="Processing Reels", progress=0, message="Starting pipeline...")

        indexed_count = indexer.count()
        base_time = int(time.time() * 1000)
        
        i = 0

        with yt_dlp.YoutubeDL(dl.get_ydl_opts()) as ydl:
            while True:
                try:
                    reel = _pipeline_queue.get_nowait()
                except queue.Empty:
                    break
                    
                i += 1
                total = _state["total"] # Refresh total
                
                shortcode = reel.get("shortcode")
                if not shortcode:
                    continue

                _update(progress=i-1, message=f"Downloading {i}/{total}: {shortcode}")
                fake_timestamp = str(base_time - i)
                dl.download_one(ydl, reel, fake_timestamp)

                mp4_path = REELS_DIR / f"{shortcode}.mp4"
                meta_path = REELS_DIR / f"{shortcode}_meta.json"
                
                if mp4_path.exists():
                    _update(message=f"Transcribing {i}/{total}: {shortcode}")
                    data = extractor.process_one(str(mp4_path), str(meta_path), str(THUMBS_DIR))
                    out_json = PROCESSED_DIR / f"{shortcode}.json"
                    with open(out_json, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    
                    _update(message=f"Indexing {i}/{total}: {shortcode}")
                    if indexer.index_one(out_json):
                        indexed_count += 1
                
                _update(progress=i, reels_indexed=indexed_count, message=f"Finished {i}/{total}: {shortcode}")

        final = indexer.count()
        _update(
            status="done",
            phase=3,
            phase_name="Ready to Chat",
            progress=total,
            total=total,
            message=f"✓ {final} reels indexed — ready to chat!",
        )

    except Exception as e:
        _update(status="error", error=str(e), message=f"Pipeline failed: {e}")
        traceback.print_exc()


# ── Static asset catch-all (CSS, JS, fonts, images) ───────────────────────────
@app.get("/{filepath:path}", include_in_schema=False)
async def static_files(filepath: str):
    # Don't accidentally catch API or page routes
    if filepath.startswith("api/") or filepath in ("app", "thumbs"):
        raise HTTPException(404)
    file = WEBSITE_DIR / filepath
    if file.exists() and file.is_file():
        return FileResponse(file)
    raise HTTPException(404, f"File not found: {filepath}")

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os as _os
    _os.environ["PYTHONDONTWRITEBYTECODE"] = "1"   # no stale .pyc files
    print("\n🎬  ReelMind is starting…")
    print("    Server → http://localhost:8000")
    print("    App    → http://localhost:8000/app\n")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, log_level="warning")
