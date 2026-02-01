"""
Конфиг категорий и источников.
"""

# ─── Источники и их паттерны статей ───────────────────

SOURCES = {
    "kun.uz": {
        "article_pattern": r'https?://kun\.uz/news/\d{4}/\d{2}/\d{2}/.+',
        "pagination_buttons": ["Ko'proq yangiliklar"],
        "pagination_type": "button",  # IAS (Infinite Ajax Scroll) — кнопка загружает следующую порцию
    },
    "gazeta.uz": {
        "article_pattern": r'https?://(www\.)?gazeta\.uz/oz/\d{4}/\d{2}/\d{2}/.+',
        "pagination_buttons": [],
        "pagination_type": "url",  # Простая пагинация: ?page=2, ?page=3 ...
        "pagination_param": "page",  # https://www.gazeta.uz/oz/sport/?page=2
    },
    "spot.uz": {
        "article_pattern": r'https?://(www\.)?spot\.uz/oz/\d{4}/\d{2}/\d{2}/.+',
        "pagination_buttons": ["Ko'proq yangiliklarni yuklash"],  # Исправлена опечатка (было "yangiliklar yuklash")
        "pagination_type": "button",  # JS load more кнопка
    },
    "zamon.uz": {
        "article_pattern": r'https?://zamon\.uz/detail/.+',
        "pagination_buttons": [],
        "pagination_type": "url",  # URL уже содержит ?page=1, заменяем номер
        "pagination_param": "page",  # https://zamon.uz/categories/sport?page=2
    },
    "uzdaily.uz": {
        # Исключаем section/, footer/, currency, search, lang — они не статьи
        "article_pattern": r'https?://(www\.)?uzdaily\.uz/uz/(?!section/|footer/|currency|search|lang)[a-z0-9][^/]+/$',
        "pagination_buttons": [],
        "pagination_type": "url",  # Простая пагинация: ?page=2
        "pagination_param": "page",  # https://www.uzdaily.uz/uz/section/7/?page=2
    },
    "afisha.uz": {
        "article_pattern": r'https?://(www\.)?afisha\.uz/uz/[^/]+/\d{4}/\d{2}/\d{2}/.+',
        "pagination_buttons": ["Ko'proq ko'rish"],
        "pagination_type": "button",  # Vue/Nuxt chunk-based загрузка
    },
}


# ─── Маппинг категорий на источники ───────────────────

CATEGORY_MAPPING = {
    "global": [
        ("kun.uz", "https://kun.uz/news/category/jahon"),
        ("gazeta.uz", "https://www.gazeta.uz/oz/politics/?page=1"),
        ("spot.uz", "https://www.spot.uz/oz/person/"),
        ("zamon.uz", "https://zamon.uz/categories/world?page=1"),
        ("uzdaily.uz", "https://www.uzdaily.uz/uz/section/1/?page=1"),
        ("afisha.uz", "https://www.afisha.uz/uz/gorod"),
    ],
    "business": [
        ("kun.uz", "https://kun.uz/news/category/iqtisodiyot"),
        ("gazeta.uz", "https://www.gazeta.uz/oz/economy/?page=1"),
        ("spot.uz", "https://www.spot.uz/oz/business/"),
        ("uzdaily.uz", "https://www.uzdaily.uz/uz/section/2/?page=1"),
        ("afisha.uz", "https://www.afisha.uz/uz/shops"),
    ],
    "sport": [
        ("kun.uz", "https://kun.uz/news/category/sport"),
        ("gazeta.uz", "https://www.gazeta.uz/oz/sport/?page=1"),
        ("zamon.uz", "https://zamon.uz/categories/sport?page=1"),
        ("uzdaily.uz", "https://www.uzdaily.uz/uz/section/7/?page=1"),
        ("afisha.uz", "https://www.afisha.uz/uz/sport"),
    ],
    "technology": [
        ("kun.uz", "https://kun.uz/news/category/texnologiya"),
        ("spot.uz", "https://www.spot.uz/oz/technology/"),
        ("uzdaily.uz", "https://www.uzdaily.uz/uz/section/4/?page=1"),
        ("afisha.uz", "https://www.afisha.uz/uz/techno"),
    ],
    "health": [
        ("kun.uz", "https://kun.uz/news/category/soglom-hayot"),
        ("zamon.uz", "https://zamon.uz/categories/medicine?page=1"),
    ],
    "entertainment": [
        ("kun.uz", "https://kun.uz/news/category/turizm"),
        ("gazeta.uz", "https://www.gazeta.uz/oz/culture/?page=1"),
        ("spot.uz", "https://www.spot.uz/oz/marketing/"),
        ("zamon.uz", "https://zamon.uz/categories/lifestyle?page=1"),
        ("afisha.uz", "https://www.afisha.uz/uz/children"),
    ],
    "science": [
        ("kun.uz", "https://kun.uz/news/category/talim"),
        ("afisha.uz", "https://www.afisha.uz/uz/znaniya"),
    ],
    "education": [
        ("spot.uz", "https://www.spot.uz/oz/education/"),
    ],
}


# ─── API функции ──────────────────────────────────────

def get_categories() -> list[str]:
    """Возвращает список всех доступных категорий."""
    return list(CATEGORY_MAPPING.keys())


def get_sources_for_category(category: str) -> list[tuple[str, str]]:
    """
    Возвращает список (source_name, url) для заданной категории.
    Например: [("kun.uz", "https://kun.uz/..."), ("gazeta.uz", "https://...")]
    """
    return CATEGORY_MAPPING.get(category, [])


def get_article_pattern(source_name: str) -> str | None:
    """Возвращает regex паттерн статьи для данного источника."""
    source = SOURCES.get(source_name)
    return source["article_pattern"] if source else None


def get_pagination_buttons(source_name: str) -> list[str]:
    """Возвращает список текстов кнопок пагинации для источника."""
    source = SOURCES.get(source_name)
    return source["pagination_buttons"] if source else []


def get_pagination_type(source_name: str) -> str | None:
    """Возвращает тип пагинации: 'url', 'button' или None."""
    source = SOURCES.get(source_name)
    return source.get("pagination_type") if source else None


def get_pagination_param(source_name: str) -> str | None:
    """Возвращает имя параметра пагинации для url-типа (например, 'page')."""
    source = SOURCES.get(source_name)
    return source.get("pagination_param") if source else None
