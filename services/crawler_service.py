"""
crawler_service.py
"""

import re
import sys
import asyncio
import concurrent.futures
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from playwright.async_api import async_playwright


# ─── ProactorEventLoop wrapper (Windows fix) ──────────

def _run_in_proactor(coro):
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def run_playwright_task(coro):
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return await loop.run_in_executor(executor, _run_in_proactor, coro)


# ─── Проверка URL на статью ───────────────────────────

def _is_article_url(url: str, pattern: str) -> bool:
    """Проверяет, совпадает ли URL с паттерном статьи."""
    return bool(re.match(pattern, url))


# ─── Извлечение ссылок и изображений ──────────────────

def extract_article_links(html: str, base_url: str, article_pattern: str) -> list[str]:
    """
    Extract article links from HTML.
    Works with both HTML and markdown (backwards compatible).
    Filters links by:
    1. Same domain as base_url
    2. Match article_pattern
    """
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc

    links = []
    seen = set()

    # Try HTML extraction first (for dynamic sites)
    html_pattern = r'href=["\']([^"\']+)["\']'
    html_matches = re.findall(html_pattern, html)
    
    for url in html_matches:
        url = url.strip().split('#')[0].split('?')[0]
        
        # Skip empty, relative, or non-http URLs
        if not url or not url.startswith('http'):
            # Try to make absolute URL
            if url.startswith('/'):
                url = f"https://{base_domain}{url}"
            else:
                continue
        
        if url in seen:
            continue

        parsed_url = urlparse(url)
        if parsed_url.netloc != base_domain:
            continue

        if not _is_article_url(url, article_pattern):
            continue

        seen.add(url)
        links.append(url)

    # If no HTML links found, try markdown format (backwards compatible)
    if not links:
        markdown_pattern = r'\[([^\]]+)\]\((https?://[^\)]+)\)'
        markdown_matches = re.findall(markdown_pattern, html)

        for text, url in markdown_matches:
            url = url.strip().split('#')[0].split('?')[0]

            if url in seen:
                continue

            parsed_url = urlparse(url)
            if parsed_url.netloc != base_domain:
                continue

            if not _is_article_url(url, article_pattern):
                continue

            seen.add(url)
            links.append(url)

    return links


def extract_first_image(markdown: str) -> str | None:
    """
    Извлекает качественное изображение новости (баннер), фильтруя логотипы.
    Приоритет:
    1. OG image теги
    2. Большие изображения (не логотипы)
    """
    # Ищем все изображения в markdown
    pattern = r'!\[([^\]]*)\]\((https?://[^\)]+)\)'
    matches = re.findall(pattern, markdown)
    
    if not matches:
        return None
    
    # Фильтруем логотипы и иконки по URL
    logo_keywords = ['logo', 'icon', 'avatar', 'favicon', 'sprite', 'svg', 'badge']
    
    filtered_images = []
    for alt_text, url in matches:
        url_lower = url.lower()
        
        # Пропускаем логотипы
        if any(keyword in url_lower for keyword in logo_keywords):
            continue
        
        # Пропускаем маленькие изображения по паттернам в URL
        if any(size in url_lower for size in ['_s.', '_xs.', '_thumb.', '_small.', '/i/', '/icons/']):
            continue
        
        filtered_images.append(url)
    
    # Возвращаем первое подходящее изображение
    if filtered_images:
        return filtered_images[0]
    
    # Если все отфильтровали, берем первое (но это редкий случай)
    return matches[0][1] if matches else None


def extract_og_image(html: str) -> str | None:
    """
    Извлекает OG image из HTML (Open Graph теги - самое качественное изображение новости).
    Примеры тегов:
    <meta property="og:image" content="https://example.com/image.jpg" />
    <meta name="og:image" content="https://example.com/image.jpg" />
    """
    # Паттерн для поиска og:image
    patterns = [
        r'<meta\s+property=["\']og:image["\']\s+content=["\'](https?://[^"\']+)["\']',
        r'<meta\s+name=["\']og:image["\']\s+content=["\'](https?://[^"\']+)["\']',
        r'<meta\s+content=["\'](https?://[^"\']+)["\']\s+property=["\']og:image["\']',
        r'<meta\s+content=["\'](https?://[^"\']+)["\']\s+name=["\']og:image["\']',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None


# ─── URL пагинация: сборка URL с page=N ───────────────

def _build_paginated_url(base_url: str, pagination_param: str, page_number: int) -> str:
    """
    Заменяет или добавляет параметр пагинации в URL.
    Примеры:
        _build_paginated_url("https://www.uzdaily.uz/uz/section/7/?page=1", "page", 2)
        → "https://www.uzdaily.uz/uz/section/7/?page=2"

        _build_paginated_url("https://www.gazeta.uz/oz/sport/", "page", 2)
        → "https://www.gazeta.uz/oz/sport/?page=2"

        _build_paginated_url("https://zamon.uz/categories/sport?page=1", "page", 3)
        → "https://zamon.uz/categories/sport?page=3"
    """
    parsed = urlparse(base_url)
    params = parse_qs(parsed.query)
    # parse_qs возвращает {"page": ["1"]} — берём список и заменяем
    params[pagination_param] = [str(page_number)]
    # urlencode с doseq=True: {"page": ["2"]} → "page=2"
    new_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))

async def _crawl_category_page_inner(url: str) -> str:
    """
    Crawl category page with improved JS waiting for dynamic sites.
    Uses 'load' instead of 'networkidle' for problematic sites.
    """
    # Try with 'load' first (faster, works for most sites)
    config = CrawlerRunConfig(
        cache_mode=CacheMode.DISABLED,
        wait_until="load",  # Wait for page load (not networkidle)
        page_timeout=30000,  # 30 seconds timeout
        delay_before_return_html=2.0,  # Wait 2 seconds for JS to render
    )
    
    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url, config=config)
            # Use HTML instead of markdown for better link extraction
            return result.html or ""
    except Exception as e:
        print(f"[Crawl Error with 'load'] {url}: {e}")
        print(f"[Retry] Trying with 'domcontentloaded'...")
        
        # Fallback: try with domcontentloaded (even faster)
        config_fallback = CrawlerRunConfig(
            cache_mode=CacheMode.DISABLED,
            wait_until="domcontentloaded",
            page_timeout=20000,  # 20 seconds
            delay_before_return_html=3.0,  # Wait longer for JS
        )
        
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url, config=config_fallback)
            return result.html or ""


async def crawl_category_page(url: str) -> str:
    return await run_playwright_task(_crawl_category_page_inner(url))


# ─── Пагинация ────────────────────────────────────────

async def _paginate_inner(url: str, needed: int, already_found: list[str], base_url: str, article_pattern: str, custom_buttons: list[str]) -> list[str]:
    all_links = set(already_found)
    max_pagination_attempts = 10
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", lambda r: r.abort())
        
        # Use 'load' instead of 'networkidle' to avoid timeout issues
        try:
            await page.goto(url, wait_until="load", timeout=20000)
        except Exception as e:
            print(f"[Pagination Error] Failed to load {url}: {e}")
            await browser.close()
            return list(all_links)

        for attempt in range(max_pagination_attempts):
            if len(all_links) >= needed:
                break

            next_button = await _find_pagination_element(page, custom_buttons)
            if next_button is None:
                break

            await next_button.click()
            await page.wait_for_timeout(2500)

            html_content = await page.content()
            new_links = _extract_links_from_html(html_content, base_domain, article_pattern)
            all_links.update(new_links)

        await browser.close()

    return list(all_links)


async def paginate_and_collect_links(url: str, needed: int, already_found: list[str], article_pattern: str, pagination_buttons: list[str]) -> list[str]:
    return await run_playwright_task(_paginate_inner(url, needed, already_found, url, article_pattern, pagination_buttons))


async def _find_pagination_element(page, custom_buttons: list[str]):
    """Ищет кнопку пагинации."""
    # 1. Custom buttons
    for text in custom_buttons:
        buttons = page.locator(f'button:has-text("{text}")')
        if await buttons.count() > 0:
            return buttons.first
        links = page.locator(f'a:has-text("{text}")')
        if await links.count() > 0:
            return links.first

    # 2. Стандартные
    pagination_texts = [
        "показать ещё", "показать еще", "показать больше",
        "загрузить ещё", "загрузить еще",
        "load more", "show more", "next",
        "далее", "следующая", "следующий",
    ]
    for text in pagination_texts:
        buttons = page.locator(f'button:has-text("{text}")')
        if await buttons.count() > 0:
            return buttons.first
        links = page.locator(f'a:has-text("{text}")')
        if await links.count() > 0:
            return links.first

    # 3. aria-label
    for text in pagination_texts:
        elements = page.locator(f'[aria-label*="{text}"]')
        if await elements.count() > 0:
            return elements.first

    # 4. Numbered
    page_numbers = page.locator('a[href*="page="], a[href*="?p="]')
    if await page_numbers.count() > 0:
        all_nums = await page_numbers.all()
        if all_nums:
            return all_nums[-1]

    # 5. CSS
    pagination_classes = [
        ".pagination .next",
        ".paginate .next",
        ".nav-pagination .next",
        '[class*="pagination"] [class*="next"]',
        '[class*="paginate"] [class*="next"]',
        ".btn-load-more",
        '[class*="load-more"]',
        '[class*="loadmore"]',
    ]
    for selector in pagination_classes:
        elements = page.locator(selector)
        if await elements.count() > 0:
            return elements.first

    return None


def _extract_links_from_html(html: str, base_domain: str, article_pattern: str) -> set[str]:
    """Извлекает ссылки из HTML, фильтруя по домену и паттерну статьи."""
    pattern = r'href=["\']((https?://[^"\']+))["\']'
    matches = re.findall(pattern, html)

    links = set()
    for url, _ in matches:
        url = url.strip().split('#')[0]
        parsed = urlparse(url)
        if parsed.netloc != base_domain:
            continue
        if not _is_article_url(url, article_pattern):
            continue
        links.add(url)

    return links


# ─── Парсинг статьи ───────────────────────────────────

async def _parse_article_inner(url: str) -> dict:
    config = CrawlerRunConfig(cache_mode=CacheMode.DISABLED)
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=config)
        markdown = result.markdown or ""
        html = result.html or ""
        
        # Приоритет 1: OG image из HTML (самое качественное)
        image_url = extract_og_image(html)
        
        # Приоритет 2: Фильтрованное изображение из markdown
        if not image_url:
            image_url = extract_first_image(markdown)
        
        return {
            "url": url,
            "raw_text": markdown,
            "image_url": image_url,
        }


async def parse_article(url: str) -> dict:
    return await run_playwright_task(_parse_article_inner(url))


# ─── Основной поток для одного источника ──────────────

async def collect_articles_from_source(
    source_name: str,
    category_url: str,
    limit: int,
    article_pattern: str,
    pagination_buttons: list[str],
    pagination_type: str | None = None,
    pagination_param: str | None = None,
) -> list[dict]:
    """
    Собирает статьи с одного источника.
    Поддерживает два режима пагинации:
      - "url"    → сам меняем ?page=N в URL, по кругу через crawl4ai
      - "button" → через Playwright кликаем "Ko'proq yangiliklar" и т.д.
    """
    # Шаг 1: crawl главной категории (page=1 или без page)
    html = await crawl_category_page(category_url)
    links = extract_article_links(html, category_url, article_pattern)
    print(f"[{source_name}] Найдено {len(links)} статей на странице")

    # Шаг 2: пагинация если мало статей
    if len(links) < limit:
        if pagination_type == "url" and pagination_param:
            # URL-пагинация: сам собираем ?page=2, ?page=3 ...
            print(f"[{source_name}] Нужно {limit}, есть {len(links)} → URL-пагинация")
            links = await _paginate_by_url(
                base_url=category_url,
                needed=limit,
                already_found=links,
                article_pattern=article_pattern,
                pagination_param=pagination_param,
                source_name=source_name,
            )
            print(f"[{source_name}] После URL-пагинации: {len(links)} статей")

        elif pagination_type == "button" and pagination_buttons:
            # Button-пагинация: через Playwright кликаем кнопку
            print(f"[{source_name}] Нужно {limit}, есть {len(links)} → кнопка пагинации")
            links = await paginate_and_collect_links(
                url=category_url,
                needed=limit,
                already_found=links,
                article_pattern=article_pattern,
                pagination_buttons=pagination_buttons,
            )
            print(f"[{source_name}] После button-пагинации: {len(links)} статей")

    links = links[:limit]
    print(f"[{source_name}] Парсим {len(links)} статей...")

    # Шаг 3: парсим каждую статью
    result = []
    for url in links:
        try:
            article = await parse_article(url)
            raw = article.get("raw_text", "")
            if len(raw.strip()) < 100:
                print(f"[{source_name}] Пропускаем (мало текста): {url}")
                continue
            article["source_name"] = source_name
            result.append(article)
            print(f"[{source_name}] OK ({len(raw)} chars): {url}")
        except Exception as e:
            print(f"[{source_name} Error] {url}: {e}")
            continue

    return result


async def _paginate_by_url(
    base_url: str,
    needed: int,
    already_found: list[str],
    article_pattern: str,
    pagination_param: str,
    source_name: str,
    max_pages: int = 10,
) -> list[str]:
    """
    URL-пагинация: крутим ?page=2, ?page=3 ... пока не набрём нужное количество.
    Если на очередной странице 0 новых статей — останавливаемся.
    """
    all_links = list(already_found)
    seen = set(already_found)

    for page_num in range(2, max_pages + 2):  # начинаем с page=2
        if len(all_links) >= needed:
            break

        paginated_url = _build_paginated_url(base_url, pagination_param, page_num)
        print(f"[{source_name}] Пагинация page={page_num}: {paginated_url}")

        try:
            html = await crawl_category_page(paginated_url)
            new_links = extract_article_links(html, base_url, article_pattern)
        except Exception as e:
            print(f"[{source_name}] Ошибка на page={page_num}: {e}")
            break

        added = 0
        for link in new_links:
            if link not in seen:
                seen.add(link)
                all_links.append(link)
                added += 1

        print(f"[{source_name}] page={page_num}: +{added} новых (всего {len(all_links)})")

        # Если ничего нового — конец пагинации
        if added == 0:
            print(f"[{source_name}] Конец пагинации на page={page_num}")
            break

    return all_links
