@echo off
rem One-time setup on Windows (cmd.exe): build, Telegram login for MRKT, start, self-check.
rem Usage: scripts\setup.cmd   (Docker Desktop must be running; .env must exist in the project folder)
setlocal
cd /d "%~dp0.."

echo ==^> Checking Docker
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker is not running. Start Docker Desktop, wait for "Engine running" and try again.
    exit /b 1
)

if not exist .env (
    if exist .env.txt (
        echo Found .env.txt - rename it: ren .env.txt .env
    ) else (
        echo File .env not found in %CD%
    )
    exit /b 1
)

for %%K in (TELEGRAM_BOT_TOKEN ADMIN_USER_IDS POSTGRES_PASSWORD GIFTWIKI_API_KEY TELEGRAM_API_ID TELEGRAM_API_HASH) do (
    findstr /r /c:"^%%K=." .env >nul
    if errorlevel 1 (
        echo .env: %%K is empty
        exit /b 1
    )
)

echo ==^> Building the image
docker compose build
if errorlevel 1 exit /b 1

echo ==^> Telegram login for MRKT (phone number and code are typed only here)
docker compose run --rm -it bot python -m gift_sniper mrkt-login
if errorlevel 1 exit /b 1

echo ==^> Starting
docker compose up -d
if errorlevel 1 exit /b 1

echo ==^> Self-check
docker compose run --rm bot python -m gift_sniper check

echo.
echo Done. Open the bot in Telegram and send /start. Logs: docker compose logs -f bot
endlocal
