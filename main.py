import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from routers.news import router as news_router

app = FastAPI(
    title="NewsFetcher API",
    description="Парсер новостей с поддержкой пагинации и Mistral extraction",
    version="1.0.0",
)

# ─── Маршруты ─────────────────────────────────────────

app.include_router(news_router)

# ─── Статика + UI ─────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Раздаём единственный HTML файл (UI для тестирования)."""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# ─── Health check ─────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}
