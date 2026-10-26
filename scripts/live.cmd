@echo off
rem Real purchases on Windows (cmd.exe): sets RUN_MODE=live in .env and restarts the bot.
rem Usage: scripts\live.cmd       real purchases, only within the limits set in the bot
rem        scripts\live.cmd off   back to the test mode (RUN_MODE=dry_run)
setlocal
set MODE=live
if /i "%~1"=="off" set MODE=dry_run
cd /d "%~dp0.."

echo ==^> Checking Docker
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker is not running. Start Docker Desktop, wait for "Engine running" and try again.
    exit /b 1
)
if not exist .env (
    echo File .env not found in "%CD%"
    exit /b 1
)

echo ==^> RUN_MODE=%MODE% in .env
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Join-Path (Get-Location) '.env'; $t = [IO.File]::ReadAllText($p); $line = 'RUN_MODE=%MODE%'; if ($t -match '(?m)^RUN_MODE=') { $t = [regex]::Replace($t, '(?m)^RUN_MODE=[^\r\n]*', $line) } else { if ($t.Length -gt 0 -and -not $t.EndsWith([string][char]10)) { $t += [Environment]::NewLine }; $t += $line + [Environment]::NewLine }; [IO.File]::WriteAllText($p, $t)"
if errorlevel 1 goto edit_failed
findstr /r /c:"^RUN_MODE=%MODE%" .env >nul
if errorlevel 1 goto edit_failed

echo ==^> Restarting the bot
docker compose up -d --force-recreate bot
if errorlevel 1 exit /b 1

echo.
if "%MODE%"=="live" (
    echo Real purchases are ON: the bot spends TON from your MRKT balance, only within the limits set in the bot.
    echo The badge at the top of the mini app must be green. If it is not, turn on the buy switch on its Profile tab.
    echo Back to the test mode: scripts\live.cmd off
) else (
    echo Test mode is ON: purchases are only simulated.
)
endlocal
exit /b 0

:edit_failed
echo Could not change .env: open it in Notepad, set RUN_MODE=%MODE% and run: docker compose up -d
exit /b 1
