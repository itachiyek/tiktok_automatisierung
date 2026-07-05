# Einmaliges Setup des PO-Token-Providers (bgutil) fuer yt-dlp/YouTube-Downloads.
# Start:  powershell -ExecutionPolicy Bypass -File "C:\Users\Yunus\Documents\tiktok_automatisierung\scripts\setup_potoken.ps1"
$ErrorActionPreference = "Continue"
$dir = "C:\Users\Yunus\bgutil-ytdlp-pot-provider"
$log = "C:\Users\Yunus\Documents\tiktok_automatisierung\data\potoken_setup.log"
"=== PO-Token Provider Setup $(Get-Date) ===" | Out-File -FilePath $log -Encoding utf8

function Log($m) { $m | Tee-Object -FilePath $log -Append }

Log ("git : " + (git --version 2>&1))
Log ("node: " + (node --version 2>&1) + "   npm: " + (npm --version 2>&1))

if (Test-Path $dir) { Log "Entferne alten Ordner ..."; Remove-Item -Recurse -Force $dir }

Log "== git clone =="
git clone --depth 1 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git $dir 2>&1 | Tee-Object -FilePath $log -Append

$srv = Join-Path $dir "server"
if (-not (Test-Path $srv)) {
    Log "FEHLER: 'server' fehlt nach dem Clone."
    Log ("Top-Level-Inhalt: " + (((Get-ChildItem $dir -ErrorAction SilentlyContinue).Name) -join ", "))
    "SETUP_RESULT=FAIL_CLONE" | Tee-Object -FilePath $log -Append
    exit 1
}

Set-Location $srv
Log "== npm install =="
npm install 2>&1 | Tee-Object -FilePath $log -Append

$target = Join-Path $srv "build\generate_once.js"
Log "== build: npm run build =="
npm run build 2>&1 | Tee-Object -FilePath $log -Append
if (-not (Test-Path $target)) {
    Log "== build-Fallback: npx tsc =="
    npx --yes tsc 2>&1 | Tee-Object -FilePath $log -Append
}

$ok = Test-Path $target
Log ("generate_once.js vorhanden: " + $ok + "  ($target)")
if ($ok) { "SETUP_RESULT=OK" | Tee-Object -FilePath $log -Append }
else { "SETUP_RESULT=FAIL_BUILD" | Tee-Object -FilePath $log -Append }
Log "== fertig =="
