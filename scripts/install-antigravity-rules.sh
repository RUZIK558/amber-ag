#!/usr/bin/env bash
# Устанавливает глобальные правила Antigravity в ~/.gemini/config/rules/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/extras/antigravity-rules/00-execution-policy.md"
DEST="$HOME/.gemini/config/rules"

[ -f "$SRC" ] || { echo "Не найден файл правил: $SRC" >&2; exit 1; }

mkdir -p "$DEST"
if [ -f "$DEST/00-execution-policy.md" ]; then
    mkdir -p "$DEST/.backup"
    cp "$DEST/00-execution-policy.md" "$DEST/.backup/00-execution-policy.md.$(date +%Y%m%d-%H%M%S)"
    echo "Старая версия сохранена в $DEST/.backup/"
fi
cp "$SRC" "$DEST/00-execution-policy.md"
chmod 644 "$DEST/00-execution-policy.md"

echo "Правила установлены: $DEST/00-execution-policy.md"
echo "Antigravity перечитывает правила перед каждым ходом — перезапуск не нужен."
