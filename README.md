# tiktok_automatisierung

Automatisierte Highlight-Clips deutscher Creator (**Trymacs · Eligella · Sidney**) für TikTok —
als Partnermodell mit Einwilligung der Creator.

**Pipeline:** Quellen überwachen (Twitch/YouTube) → Highlights erkennen → vertikal (9:16)
schneiden + Untertitel + Creator-Credit → Texte & Hashtags per KI (Claude) → Qualitäts-/Review-Gate
→ Upload (TikTok Content Posting API) → Analyse.

➡️ Strategie & Hintergrund: **[`PLAN.md`](./PLAN.md)**

---

## Schnellstart

```bash
# 1) Abhängigkeiten
python3 -m pip install -r requirements.txt
sudo apt-get install ffmpeg          # bzw. brew install ffmpeg

# 2) Konfiguration
cp config/creators.example.yaml config/creators.yaml   # Creator/Accounts anpassen
cp .env.example .env                                    # API-Keys eintragen (s. u.)

# 3) Prüfen, was noch fehlt (zeigt jeden Key einzeln an)
python3 -m src.cli check

# 4) Trockenlauf – zeigt nur, welche Quellen gefunden würden (nichts wird hochgeladen)
python3 -m src.cli run --dry-run

# 5) Echter Lauf für einen Creator (schneidet Clips, lädt NICHTS automatisch hoch)
python3 -m src.cli run --creator trymacs --limit 3

# 6) Review & Upload
python3 -m src.cli clips --status pending_review      # erzeugte Clips ansehen
python3 -m src.cli approve 1 2 3                       # freigeben
python3 -m src.cli upload-approved --creator trymacs  # privat hochladen (vor Audit)
# nach bestandenem TikTok-Audit zusätzlich: --public
```

> Sicher per Default: Clips landen in der Review-Queue (`pending_review`) und werden **nicht**
> automatisch gepostet. Vollautomatik aktivierst du mit `run --auto-upload` (nur empfehlenswert,
> wenn du der Trefferquote vertraust und Tokens vorliegen).

---

## 🔑 Welche API-Keys brauchst du? (in `.env` eintragen)

| Key | Wofür | Woher | Pflicht? |
|---|---|---|---|
| `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` | Twitch-Clips & VODs abrufen | https://dev.twitch.tv/console/apps | **Ja** (Hauptquelle) |
| `YOUTUBE_API_KEY` | neue YouTube-Uploads erkennen | https://console.cloud.google.com → „YouTube Data API v3" aktivieren → API-Key | Optional (nur mit `--youtube`) |
| `ANTHROPIC_API_KEY` | Caption & Hashtags per Claude | https://console.anthropic.com | Empfohlen (ohne → Template-Texte) |
| `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET` | App-Identität der TikTok-API | https://developers.tiktok.com → App → **Content Posting API** beantragen | **Ja** (zum Hochladen) |
| `TIKTOK_ACCESS_TOKEN_<ID>` | Upload-Token pro Creator-Account (Scope `video.publish`) | OAuth-Flow je TikTok-Konto; `<ID>` = `id` aus `creators.yaml` (GROSS), z. B. `TIKTOK_ACCESS_TOKEN_TRYMACS` | **Ja** (pro Konto) |
| `TIKTOK_REFRESH_TOKEN_<ID>` | Token-Erneuerung | gleicher OAuth-Flow | Empfohlen |

**Wichtig zu TikTok:** Die Freigabe der Content Posting API dauert i. d. R. **2–6 Wochen** (Audit).
**Jetzt beantragen.** Vor dem Audit sind Uploads nur privat sichtbar (`SELF_ONLY`) — der Code
nutzt das automatisch als Default; `--public` erst nach bestandenem Audit.

**Was du NICHT als Key brauchst:** Download (`yt-dlp`) und Untertitel (`faster-whisper`) laufen
lokal ohne Key. `ffmpeg` muss installiert sein.

---

## Struktur

```
src/
  config.py            # creators.yaml + .env laden, Key-Helper
  models.py            # SourceItem / Segment / Clip / ClipMeta
  db.py                # SQLite: Dedup + Clip-Status
  ingest/              # twitch.py · youtube.py · downloader.py (yt-dlp)
  highlight/           # audio_energy.py (Erkennung) · selector.py
  edit/                # editor.py (ffmpeg 9:16) · subtitles.py (Whisper→ASS)
  metadata/            # generator.py (Claude → Caption/Hashtags, Fallback-Template)
  review/              # quality_gate.py (Dedup, Länge, Review-Status)
  upload/              # tiktok.py (Content Posting API, Direct Post)
  analytics/           # collector.py (Views/Engagement zurücklesen)
  pipeline.py          # Orchestrator
  cli.py               # Kommandozeile
tests/                 # Logik-Tests (ohne Netz/Keys):  python3 -m pytest -q
config/creators.example.yaml
```

## Status
- [x] Projektplan (`PLAN.md`)
- [x] Lauffähige Pipeline + CLI + Tests
- [ ] `.env` mit echten API-Keys (siehe Tabelle oben)
- [ ] Creator-Vereinbarungen (schriftlich)
- [ ] TikTok Content Posting API beantragt (Audit 2–6 Wochen)
