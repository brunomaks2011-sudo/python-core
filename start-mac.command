#!/bin/bash
# Подвійний клік у Finder запускає сайт (Mac). На Linux: ./start-mac.command
cd "$(dirname "$0")" || exit 1
if ! command -v node >/dev/null 2>&1; then
  echo "Не знайдено Node.js. Встановіть версію LTS з https://nodejs.org і запустіть цей файл ще раз."
  read -r -p "Натисніть Enter, щоб закрити"
  exit 1
fi
if [ ! -d node_modules ]; then
  echo "Встановлюю залежності, це займе кілька хвилин..."
  npm install || { read -r -p "Натисніть Enter, щоб закрити"; exit 1; }
fi
node scripts/local-start.mjs
