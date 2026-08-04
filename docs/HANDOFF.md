# Session-Übergabe / Kontext für neue Session

> Kopiere diese Datei (oder ihren Inhalt) in eine neue Session, um nahtlos weiterzumachen.
> Stand: 2026-06-29 · Branch: `claude/tiktok-clips-automation-plan-6fmit4`

## Projektziel
Automatisiert Highlight-Clips deutscher Creator (**Trymacs, Eligella, Sidney**) aus deren
Twitch-/YouTube-Inhalten schneiden, vertikal (9:16) mit Untertiteln aufbereiten, per KI
Caption + Hashtags erzeugen und auf TikTok hochladen. **Geld** über TikTok Creator Rewards,
Revenue-Share mit den Creatorn, später Markendeals.

## Wichtige Entscheidungen / Annahmen
- **Einwilligung der Creator liegt vor** → legales Partnermodell (kein Reupload ohne Erlaubnis).
  TODO: schriftliche Vereinbarung pro Creator (Scope, Accounts, Revenue-Share).
- **Pro Creator ein eigener TikTok-Clip-Account** (`@trymacs.clips` etc.).
- **Twitch-Community-Clips** = primäre Quelle (bereits kuratierte Highlights, günstigster Start).
- **Hybrid Build-vs-Buy**: eigene Pipeline ist gebaut; fertige KI-Tools (Eklipse/OpusClip) optional.
- **State** in SQLite (`data/clips.db`), später Migration zu Supabase möglich.
- **Sicherheits-Default**: Clips landen in Review-Queue (`pending_review`), werden NICHT
  automatisch gepostet; vor TikTok-Audit nur privat (`SELF_ONLY`).

## Was bereits gebaut & gepusht ist (lauffähig, 9 Tests grün)
```
PLAN.md                      # ausführlicher Strategie-/Architekturplan
README.md                    # Setup, Befehle, API-Key-Tabelle
.env.example                 # alle benötigten Keys
config/creators.example.yaml # Profile Trymacs/Eligella/Sidney
requirements.txt             # deps (+ ffmpeg als Systemtool nötig)
src/
  config.py        # creators.yaml + .env laden, Key-Helper
  models.py        # SourceItem / Segment / Clip / ClipMeta
  db.py            # SQLite: Dedup + Clip-Status
  ingest/twitch.py # Helix: Community-Clips + VODs
  ingest/youtube.py# Data API: neue Uploads
  ingest/downloader.py # yt-dlp
  highlight/audio_energy.py # RMS-Peak-Erkennung (+ reine, testbare pick_segments)
  highlight/selector.py
  edit/editor.py   # ffmpeg 9:16 (face_split = Standard, blur_pad/crop)
  edit/facecam.py  # Gesicht des Streamers finden (YuNet) + Split-Layout rechnen
  edit/subtitles.py# faster-whisper -> ASS (gebrannte Untertitel)
  metadata/generator.py # Claude API -> Caption/Hashtags (Fallback ohne Key)
  review/quality_gate.py # Dedup, Länge, Review-Status
  upload/tiktok.py # Content Posting API (Direct Post, FILE_UPLOAD)
  upload/tiktok_auth.py # OAuth-Helfer: erzeugt Access-/Refresh-Token pro Konto
  analytics/collector.py # Views/Engagement zurücklesen
  pipeline.py      # Orchestrator
  cli.py           # CLI
tests/test_pipeline.py
docs/HANDOFF.md    # diese Datei
```

## CLI-Befehle
```bash
python3 -m src.cli check                 # zeigt, welche Keys/Tools fehlen
python3 -m src.cli auth --creator trymacs# TikTok-Konto autorisieren -> Token-Zeilen für .env
python3 -m src.cli run --dry-run         # nur Ingest zeigen (nichts schneiden/posten)
python3 -m src.cli run --creator trymacs --limit 3   # Clips erzeugen (kein Auto-Upload)
python3 -m src.cli clips --status pending_review      # Clips ansehen
python3 -m src.cli approve 1 2 3         # freigeben
python3 -m src.cli upload-approved --creator trymacs # hochladen (privat; --public erst nach Audit)
python3 -m pytest -q                     # Tests
```

## API-Keys (in .env, Vorlage .env.example)
| Key | Woher | Pflicht |
|---|---|---|
| TWITCH_CLIENT_ID / _SECRET | dev.twitch.tv/console/apps | ja (Hauptquelle) |
| YOUTUBE_API_KEY | console.cloud.google.com → YouTube Data API v3 | optional (--youtube) |
| ANTHROPIC_API_KEY | console.anthropic.com | empfohlen (sonst Template-Texte) |
| TIKTOK_CLIENT_KEY / _SECRET | developers.tiktok.com → Manage apps → App → Credentials | ja |
| TIKTOK_REDIRECT_URI | muss identisch im Portal sein (Default http://localhost:8080/callback) | ja für auth |
| TIKTOK_ACCESS_TOKEN_<ID> | erzeugt durch `python3 -m src.cli auth --creator <id>` | ja (pro Konto) |
| TIKTOK_REFRESH_TOKEN_<ID> | gleicher auth-Befehl | empfohlen |

**Merke:** Client Key/Secret = App-Ausweis (aus Portal). Access Token = Erlaubnis pro Konto
(entsteht nur durch Login des Kontos via `auth`). Beide sind NICHT dasselbe.

## Aktueller Stand des Nutzers
- TikTok-App erstellt, **Client Key + Secret vorhanden**.
- Nächster Schritt: Keys in `.env`, dann `auth --creator <id>` pro Konto laufen lassen.
- Offen: Scope `video.publish` in der App aktivieren (Content Posting API als Product hinzufügen),
  TikTok-Audit für öffentliche Posts beantragen (dauert 2–6 Wochen).

## Offene To-dos / mögliche nächste Schritte
- [ ] `.env` mit echten Keys füllen, `check` grün bekommen.
- [ ] TikTok Content Posting API beantragen (Audit, langwierig → früh starten).
- [ ] Schriftliche Creator-Vereinbarungen.
- [ ] Erst-Lauf für 1 Creator, Trefferquote der Clips prüfen.
- [ ] Optional: Scheduler (cron/n8n) für tägliche Läufe.
- [ ] Optional: Review-Dashboard (z. B. Next.js/Vercel).
- [ ] Optional: TikTok-Token-Auto-Refresh nutzen (refresh_access_token in tiktok_auth.py).
- [ ] Optional: bessere Highlight-Erkennung (Twitch-Chat-Velocity statt nur Audio).
- [ ] Musik/GEMA-Erkennung & Stummschaltung (Rest-Risiko bei Stream-Hintergrundmusik).

## Lokal starten (neue Session)
```bash
git clone <repo> && cd tiktok_automatisierung
git checkout claude/tiktok-clips-automation-plan-6fmit4
python3 -m pip install -r requirements.txt
sudo apt-get install ffmpeg   # bzw. brew install ffmpeg
cp config/creators.example.yaml config/creators.yaml
cp .env.example .env          # Keys eintragen
python3 -m src.cli check
```
