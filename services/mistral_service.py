"""
mistral_service.py
"""

import json
import asyncio
import re
from mistralai import Mistral
from core.settings import settings


client = Mistral(api_key=settings.mistral_api_key)


EXTRACTION_PROMPT_TEMPLATE = """You are a precise news article extraction tool.

**CRITICAL RULES:**
1. Extract the publication date in YYYY-MM-DD format. Look for dates in:
   - Article metadata
   - URLs (e.g., /2026/01/31/)
   - Timestamps in the text
   - If you find ANY date reference, extract it. DO NOT return null unless absolutely no date exists.

2. Content must be EXACTLY 1500 characters or less. If longer, intelligently summarize the key points.

3. Return ONLY valid JSON. No markdown, no explanations, no code blocks.

**Required JSON format:**
{{
  "title": "Article title here",
  "content": "Cleaned article text, max 1500 chars",
  "date_of_publication": "YYYY-MM-DD or null",
  "language": "uz/ru/en"
}}

**Text cleaning:**
- Remove navigation, ads, footers, cookie banners, social media
- Keep only the article title and main body
- Fix any encoding/formatting issues

**URL hint for date extraction:**
Source URL: {source_url}

**Raw text:**
---
{raw_text}
---

JSON:"""


# ─── Retry с backoff для 429 ──────────────────────────

async def _call_mistral_with_retry(prompt: str, max_retries: int = 5) -> str:
    """
    Вызов Mistral с автоматическим retry при 429 (rate limit).
    Экспоненциальный backoff: 2s, 4s, 8s, 16s, 32s
    """
    for attempt in range(max_retries):
        try:
            result = await asyncio.to_thread(_call_mistral_sync, prompt)
            return result
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "rate_limit" in error_msg.lower():
                wait_time = 2 ** (attempt + 1)
                print(f"[Mistral] Rate limit hit, retry {attempt + 1}/{max_retries} через {wait_time}s...")
                await asyncio.sleep(wait_time)
                continue
            raise
    raise Exception("Mistral: исчерпаны все попытки retry")


def _call_mistral_sync(prompt: str) -> str:
    response = client.chat.complete(
        model="mistral-small-latest",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=2000,
    )
    return response.choices[0].message.content


# ─── Extraction ───────────────────────────────────────

async def extract_article_with_mistral(
    raw_text: str,
    category: str,
    source_url: str,
    source_name: str,
    image_url: str | None,
) -> dict | None:
    if not raw_text or len(raw_text.strip()) < 100:
        return None

    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        raw_text=raw_text[:8000],
        source_url=source_url,
    )

    try:
        response = await _call_mistral_with_retry(prompt)
        parsed = _parse_mistral_response(response)
        if parsed is None:
            return None

        # Если Mistral не нашёл дату, пробуем извлечь из URL
        if not parsed.get("date_of_publication"):
            parsed["date_of_publication"] = _extract_date_from_url(source_url)

        # Обрезаем контент если он всё ещё длинный
        if len(parsed["content"]) > 1500:
            parsed["content"] = parsed["content"][:1497] + "..."

        parsed["category"] = category
        parsed["source_url"] = source_url
        parsed["source_name"] = source_name
        parsed["image_url"] = image_url

        return parsed

    except Exception as e:
        print(f"[Mistral Error] {source_url}: {e}")
        return None


def _extract_date_from_url(url: str) -> str | None:
    """Пытается извлечь дату из URL паттернами вроде /2026/01/31/"""
    pattern = r'/(\d{4})/(\d{2})/(\d{2})/'
    match = re.search(pattern, url)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month}-{day}"
    return None


def _parse_mistral_response(response_text: str) -> dict | None:
    if not response_text:
        return None

    text = response_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        data = json.loads(text)
        if not data.get("title") or not data.get("content"):
            return None

        if len(data["content"].strip()) < 50:
            return None

        return {
            "title": data.get("title", ""),
            "content": data.get("content", ""),
            "date_of_publication": data.get("date_of_publication"),
            "language": data.get("language", "unknown"),
        }
    except json.JSONDecodeError:
        return None


# ─── Batch: последовательно с задержкой ───────────────

async def process_articles_batch(
    raw_articles: list[dict],
    category: str,
) -> list[dict]:
    """
    Обрабатывает статьи ПОСЛЕДОВАТЕЛЬНО с маленькой задержкой между запросами.
    """
    processed = []

    for i, raw in enumerate(raw_articles):
        print(f"[Mistral] Обработка {i + 1}/{len(raw_articles)}: {raw.get('url', '')[:80]}")

        result = await extract_article_with_mistral(
            raw_text=raw.get("raw_text", ""),
            category=category,
            source_url=raw.get("url", ""),
            source_name=raw.get("source_name", "unknown"),
            image_url=raw.get("image_url"),
        )

        if result:
            processed.append(result)
            print(f"[Mistral] OK: {result['title'][:60]}")
        else:
            print(f"[Mistral] Пропущена")

        await asyncio.sleep(1.0)

    return processed
