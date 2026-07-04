#!/usr/bin/env bash
# Einmal-Setup: installiert ffmpeg + Python-Abhängigkeiten, damit die Pipeline
# schneiden (ffmpeg), Quellen laden (yt-dlp) und via Zernio posten kann.
#
# Nutzung:   bash scripts/setup.sh
# Danach:    echo 'ZERNIO_API_KEY=sk_...' > .env
#            python3 -m src.cli zernio-accounts
#            python3 -m src.cli auto            # bzw.  post --file clip.mp4 --caption "..."
#
# Voraussetzung: Netzzugang zu zernio.com, api.twitch.tv, *.youtube.com u. a.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== 1/2  ffmpeg installieren =="
if command -v ffmpeg >/dev/null 2>&1; then
  echo "   ffmpeg bereits vorhanden: $(ffmpeg -version | head -1)"
elif command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y && sudo apt-get install -y ffmpeg
elif command -v brew >/dev/null 2>&1; then
  brew install ffmpeg
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y ffmpeg
else
  echo "   ⚠️  Kein bekannter Paketmanager. ffmpeg bitte manuell installieren."
fi

echo "== 2/2  Python-Abhängigkeiten =="
python3 -m pip install -r requirements.txt

echo
echo "✅ Fertig. Als Nächstes:"
echo "   echo 'ZERNIO_API_KEY=sk_...' > .env"
echo "   python3 -m src.cli check"
echo "   python3 -m src.cli zernio-accounts"
echo "   python3 -m src.cli auto            # Highlights schneiden + via Zernio planen"
