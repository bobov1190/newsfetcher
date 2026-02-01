from fastapi import APIRouter, HTTPException
from app.schemas import FetchNewsRequest, FetchNewsResponse, ArticleOut, CategoriesResponse
from core.categories import (
    get_categories,
    get_sources_for_category,
    get_article_pattern,
    get_pagination_buttons,
    get_pagination_type,
    get_pagination_param,
)
from core.settings import settings, get_default_date_from, get_default_date_to
from services.crawler_service import collect_articles_from_source
from services.mistral_service import process_articles_batch

router = APIRouter(prefix="/api", tags=["news"])


# ─── GET /api/categories ──────────────────────────────

@router.get("/categories", response_model=CategoriesResponse)
async def list_categories():
    """
    Возвращает категории в формате dict[str, str].
    Ключ - название категории, значение - список источников.
    """
    categories_dict = {}
    for cat in get_categories():
        sources = get_sources_for_category(cat)
        source_names = ", ".join([s[0] for s in sources])
        categories_dict[cat] = source_names
    return {"categories": categories_dict}


# ─── POST /api/fetch ──────────────────────────────────

@router.post("/fetch", response_model=FetchNewsResponse)
async def fetch_news(request: FetchNewsRequest):
    # Валидация категории
    sources = get_sources_for_category(request.category)
    if not sources:
        available = get_categories()
        raise HTTPException(
            status_code=400,
            detail=f"Категория '{request.category}' не найдена. Доступные: {available}"
        )

    # Резолвим параметры
    limit = request.limit or settings.default_limit
    date_from = request.date_from or get_default_date_from()
    date_to = request.date_to or get_default_date_to()

    print(f"[Fetch] Категория '{request.category}' → {len(sources)} источников, нужно {limit} статей")

    # Собираем статьи со всех источников параллельно
    # Стратегия: даём каждому источнику больший лимит, чтобы набрать нужное количество
    import asyncio
    
    # Берём в 2 раза больше с каждого источника для страховки
    limit_per_source = max(5, (limit * 2) // len(sources))
    
    tasks = []
    for source_name, source_url in sources:
        pattern = get_article_pattern(source_name)
        buttons = get_pagination_buttons(source_name)
        pagination_type = get_pagination_type(source_name)
        pagination_param = get_pagination_param(source_name)
        task = collect_articles_from_source(
            source_name=source_name,
            category_url=source_url,
            limit=limit_per_source,
            article_pattern=pattern,
            pagination_buttons=buttons,
            pagination_type=pagination_type,
            pagination_param=pagination_param,
        )
        tasks.append(task)

    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Объединяем результаты
    raw_articles = []
    for result in all_results:
        if isinstance(result, Exception):
            print(f"[Fetch Error] {result}")
            continue
        raw_articles.extend(result)

    if not raw_articles:
        return FetchNewsResponse(
            category=request.category,
            total_fetched=0,
            articles=[],
        )

    print(f"[Fetch] Собрано {len(raw_articles)} сырых статей, отправляем все в Mistral")

    # Mistral обработка всех raw статей
    processed = await process_articles_batch(
        raw_articles=raw_articles,
        category=request.category,
    )

    print(f"[Fetch] Mistral обработал {len(processed)}/{len(raw_articles)} статей")

    # Фильтрация по датам
    filtered = _filter_by_date(processed, date_from, date_to)
    
    # Обрезаем до запрошенного лимита уже в конце
    filtered = filtered[:limit]
    
    print(f"[Fetch] После фильтрации и обрезки: {len(filtered)} статей")

    # Формируем ответ
    articles_out = [
        ArticleOut(
            title=a["title"],
            content=a["content"],
            date_of_publication=a.get("date_of_publication"),
            category=a["category"],
            language=a.get("language", "unknown"),
            source_url=a["source_url"],
            source_name=a.get("source_name", "unknown"),
            image_url=a.get("image_url"),
        )
        for a in filtered
    ]

    return FetchNewsResponse(
        category=request.category,
        total_fetched=len(articles_out),
        articles=articles_out,
    )


# ─── Helper ───────────────────────────────────────────

def _filter_by_date(articles: list[dict], date_from: str, date_to: str) -> list[dict]:
    """Фильтрует статьи по дате публикации."""
    result = []
    for a in articles:
        pub_date = a.get("date_of_publication")
        if pub_date is None:
            result.append(a)
            continue
        if date_from <= pub_date <= date_to:
            result.append(a)
    return result
