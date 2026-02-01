from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ─── Request ─────────────────────────────────────────

class FetchNewsRequest(BaseModel):
    category: str
    limit: Optional[int] = None          # если None → берётся из settings
    date_from: Optional[str] = None      # ISO format "2025-01-20"
    date_to: Optional[str] = None


# ─── Response ────────────────────────────────────────

class ArticleOut(BaseModel):
    title: str
    content: str
    date_of_publication: Optional[str] = None
    category: str
    language: str
    source_url: str                      # оригинальная ссылка на статью
    source_name: str                     # название источника (kun.uz, gazeta.uz и т.д.)
    image_url: Optional[str] = None      # URL изображения статьи


class FetchNewsResponse(BaseModel):
    category: str
    total_fetched: int
    articles: list[ArticleOut]


class CategoriesResponse(BaseModel):
    categories: dict[str, str]           # name → sources info
