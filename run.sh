#!/bin/bash
# ─────────────────────────────────────────────────────
# NewsFetcher — setup & run
# ─────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  NewsFetcher Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Venv
if [ ! -d ".venv" ]; then
  echo "→ Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

# 2. Pip install
echo "→ Installing dependencies..."
pip install -q -r requirements.txt

# 3. Playwright browsers
echo "→ Installing Playwright browsers..."
python -m playwright install chromium 2>/dev/null || true
python -m playwright install-deps chromium 2>/dev/null || true

# 4. .env check
if [ ! -f ".env" ]; then
  echo ""
  echo "⚠  .env не найден!"
  echo "   Скопируй .env.example → .env и добавь MISTRAL_API_KEY"
  cp .env.example .env
  echo "   Создан .env из шаблона. Отредактирuj его:"
  echo "   → nano .env  (или открой в любом редакторе)"
  echo ""
  read -p "   Нажми Enter после сохранения .env..." -r
fi

# 5. Launch
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Starting server..."
echo "  UI:  http://127.0.0.1:8000"
echo "  API: http://127.0.0.1:8000/docs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
