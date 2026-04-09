#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  Запуск автотестов театрального архива
#
#  Использование:
#    ./run_tests.sh              — тесты против сервера (дефолт)
#    ./run_tests.sh -v           — подробный вывод
#    ./run_tests.sh -k archive   — только архивные тесты
#    ./run_tests.sh -k search    — только тесты поиска
#
#  Целевой сервер задаётся переменной TEST_BASE_URL:
#    TEST_BASE_URL=http://localhost:8000/api ./run_tests.sh
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTS_DIR="$SCRIPT_DIR/backend/tests"

export TEST_BASE_URL="${TEST_BASE_URL:-http://178.253.38.120/api}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Театральный архив — автотесты"
echo "  Сервер: $TEST_BASE_URL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if ! python3 -m pytest --version &>/dev/null; then
  echo "⚠  pytest не найден, устанавливаю..."
  pip install pytest -q
fi

python3 -m pytest "$TESTS_DIR" \
  --tb=short \
  --no-header \
  -rN \
  "$@"
