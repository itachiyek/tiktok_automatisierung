#!/usr/bin/env bash
# Cron-Einstieg: Highlights schneiden (1–2 min, Untertitel oben) und via Zernio
# automatisch einplanen/hochladen. Für crontab -e gedacht (siehe scripts/crontab.example).
#
# Beispiel-Cron (3x täglich):
#   0 9,14,19 * * * /pfad/zum/repo/scripts/cron_run.sh
#
# Optional per Env steuerbar:
#   CLIP_LIMIT   max. Quellen pro Creator (Standard 3)
#   CREATOR      nur ein Creator (id), sonst alle
#   AUTO_FLAGS   zusätzliche Flags (z. B. "--now" für sofort statt planen)
set -euo pipefail

# Ins Projektverzeichnis wechseln (Skript liegt in scripts/).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Optionales virtuelles Environment aktivieren, falls vorhanden.
if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

mkdir -p data
LOG="data/cron.log"

ARGS=(auto --limit "${CLIP_LIMIT:-3}")
if [ -n "${CREATOR:-}" ]; then
  ARGS+=(--creator "$CREATOR")
fi
# shellcheck disable=SC2206
ARGS+=(${AUTO_FLAGS:-})

echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) cron_run start =====" >> "$LOG"
python3 -m src.cli "${ARGS[@]}" >> "$LOG" 2>&1
echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) cron_run ende =====" >> "$LOG"
