kill -9 $(pgrep -f "telegram_bot.py") || true
sleep 5
cd "/Users/agaraman/Scripts/auto_trading"
. venv/bin/activate
python src/telegram_bot.py
