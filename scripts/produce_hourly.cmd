@echo off
REM Stuendliche Clip-Produktion (Nachschub fuer den Poster), Windows Task Scheduler.
cd /d "C:\Users\Yunus\Documents\tiktok_automatisierung"
set PYTHONIOENCODING=utf-8
"C:\Users\Yunus\AppData\Local\Programs\Python\Python312\python.exe" "scripts\produce_hourly.py" >> "data\produce.log" 2>&1
