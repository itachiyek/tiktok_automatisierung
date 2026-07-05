@echo off
REM Stuendlicher TikTok-Post ueber Zernio (aufgerufen vom Windows Task Scheduler).
cd /d "C:\Users\Yunus\Documents\tiktok_automatisierung"
set PYTHONIOENCODING=utf-8
"C:\Users\Yunus\AppData\Local\Programs\Python\Python312\python.exe" "scripts\post_hourly.py" >> "data\hourly_post.log" 2>&1
