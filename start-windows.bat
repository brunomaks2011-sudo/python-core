@echo off
chcp 65001 >nul
title Цеглинка
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo.
  echo Не знайдено Node.js. Встановіть версію LTS з https://nodejs.org і запустіть цей файл ще раз.
  echo.
  pause
  exit /b 1
)
if not exist node_modules (
  echo Встановлюю залежності, це займе кілька хвилин...
  call npm install
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
node scripts\local-start.mjs
pause
