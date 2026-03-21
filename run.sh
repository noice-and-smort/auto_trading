kill -9 $(pgrep -f "/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python /Users/agaraman/Scripts/auto_trading/telegram_bot.py");
sleep 5;
. /Users/agaraman/Scripts/auto_trading/venv/bin/activate;
python /Users/agaraman/Scripts/auto_trading/telegram_bot.py;
