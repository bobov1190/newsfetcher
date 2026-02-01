# NewsFetcher

Парсер новостей с поддержкой пагинации (Playwright) и структурированной экстракцией через Mistral.

## Быстрый старт

```bash
# 1. Скопируй .env.example → .env
cp .env.example .env

# 2. Добавь свой Mistral API key в .env
# MISTRAL_API_KEY=your_key_here

# 3. Запуск (установит всё автоматически)
chmod +x run.sh
./run.sh
```

Или руками:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python -m uvicorn main:app --reload
```

## Архитектура

```
newsfetcher/
├── main.py                  # FastAPI app
├── core/
│   ├── settings.py          # Env + defaults
│   └── categories.py        # Конфиг категорий (добавь свои тут)
├── app/
│   └── schemas.py           # Pydantic models
├── routers/
│   └── news.py              # API endpoints
├── services/
│   ├── crawler_service.py   # crawl4ai + playwright пагинация
│   └── mistral_service.py   # Mistral extraction
├── static/
│   └── index.html           # UI
└── run.sh                   # Setup + launch
```

## Как добавить новую категорию

Открой `core/categories.py` и добавь:

```python
CATEGORIES = {
    # ... существующие ...
    "mysite_topic": "https://mysite.com/news/topic",
}
```

Всё. Через UI она появится автоматически.

## API

### GET `/api/categories`
Возвращает все доступные категории.

### POST `/api/fetch`
Запрос новостей.

**Body:**
```json
{
  "category": "kun_sport",
  "limit": 20,
  "date_from": "2025-01-20",
  "date_to": "2025-01-27"
}
```

- `category` — обязательно (из списка категорий)
- `limit` — кол-во новостей (по умолчанию из .env `DEFAULT_LIMIT`)
- `date_from` / `date_to` — фильтр по дате (по умолчанию последние 7 дней)

**Response:**
```json
{
  "category": "kun_sport",
  "total_fetched": 15,
  "articles": [
    {
      "title": "...",
      "content": "...",
      "date_of_publication": "2025-01-25",
      "category": "kun_sport",
      "language": "ru",
      "source_url": "https://kun.uz/news/..."
    }
  ]
}
```

## Как работает пагинация

1. `crawl4ai` скрапит главную страницу категории → извлекаем ссылки на статьи
2. Если найдено меньше чем `limit`:
   - Playwright открывает страницу в реальном браузере
   - Ищет кнопку пагинации (несколько стратегий: текст, aria-label, CSS-классы, numbered pages)
   - Кликает → собирает новые ссылки
   - Повторяет до нужного количества
3. Каждая статья парсится отдельно через `crawl4ai`
4. Сырой текст отправляется в Mistral для structured extraction

## Настройки (.env)

| Переменная | Описание |
|---|---|
| `MISTRAL_API_KEY` | Ключ Mistral API (обязательно) |
| `DEFAULT_LIMIT` | Лимит по умолчанию (default: 50) |
| `DEFAULT_DATE_FROM` | Начальная дата (по умолчанию 7 дней назад) |
| `DEFAULT_DATE_TO` | Конечная дата (по умолчанию сегодня) |
