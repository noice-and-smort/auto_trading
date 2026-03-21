kill -9 $(pgrep -f "telegram_bot.py") || true
sleep 5
cd "$(dirname "$0")"
. venv/bin/activate
python src/telegram_bot.py
