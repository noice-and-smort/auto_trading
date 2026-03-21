# Auto Trading Telegram Bot

A Python-based Telegram bot that fetches historical and derivative stock data from the National Stock Exchange of India (NSE), specifically processing options chain data and generating summarized execution CSV files directly into a Telegram chat.

## Features
- Provides automated CSV summaries of `combined_<date>.csv` containing 25 custom calculation columns (e.g. Option Ratios F1 & F2, RSI, Open Interest, Future Turnover).
- Automatically backtracks trading holidays to accurately source option data from the preceding valid trading day (gracefully supporting the NSE shift of expiry dates to Tuesday).
- Telegram integration allowing you to request the latest market summary or fetch files via `/stocks` and `/go` commands.
- Custom stock list tracking (drop your own `stocks` file directly to the bot to dynamically watch certain tickers).

## Project Structure
```text
auto_trading/
├── src/                # Python execution logic 
├── data/               # Configuration files (e.g. 'stocks' list)
├── output/             # Output directory for combined CSV artifacts
├── .env                # Secret configurations (Token, Password)
└── run.sh              # Background execution and daemon cron wrapper
```

## Setup & Execution

### 1. Environment Configurations
This project heavily relies on secure environment variables. For safety, these are not stored in Git.
You must duplicate `.env.example` to `.env` in the root of your directory:
```bash
cp .env.example .env
```
Inside `.env`, store your GitHub Secrets / Telegram Tokens:
```env
TELEGRAM_BOT_TOKEN="your_telegram_token"
EMAIL_PASSWORD="your_email_password"
```

### 2. Python Environment
All requirements are automatically stored in `req.txt`. Run:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r req.txt
```

### 3. Startup
The easiest way to invoke this persistently on Unix systems is via the provided `run.sh`, which activates the python-virtual-environment and boots up `src/telegram_bot.py`.
```bash
bash run.sh
```
