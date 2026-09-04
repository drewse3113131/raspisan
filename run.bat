@echo off
REM Запуск бота - подставь токен
REM set BOT_TOKEN=123456:ABC-DEF...

if "%BOT_TOKEN%"=="" (
  echo [ERROR] BOT_TOKEN не задан!
  echo set BOT_TOKEN=твой_токен
  pause
  exit /b
)
python bot.py
pause
