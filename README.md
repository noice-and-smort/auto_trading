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

## Understanding the Calculated Ratios & Metrics

Your script calculates several advanced derivative metrics to predict market sentiment:

- **F1 (Change in OI %):** `(Change in OI * 100) / Open Interest`
  - *What it means:* The percentage change in Open Interest for the current month's contract.
  - *Market Prediction:* A high positive F1 with a rising price indicates a strong **Long Buildup** (bullish). A high positive F1 with a falling price indicates a **Short Buildup** (bearish). Negative F1 represents unwinding (closing positions).
- **F7 (Volume to OI Ratio):** `Number of Contracts / (Change in OI / lot_size)`
  - *What it means:* How much trading volume (churn) was required to generate the net change in open positions.
  - *Market Prediction:* A low F7 means most of the volume resulted in new open positions (high conviction). A very high F7 implies heavy intraday day-trading with little net positional commitment. 
- **F8 (Blended OI Change %):** `Total Change in OI (Current + Next) * 100 / Total Open Interest`
  - *What it means:* Similar to F1, but blends the current and next month's contracts.
  - *Market Prediction:* Highly useful during expiry week to smooth out the noise of "rollovers". It gives a truer picture of overall positional buildup across maturities.
- **F9 (Absolute OI Contract Change):** `(Change in OI + Change in OI Next) / lot_size`
  - *What it means:* The absolute net change in Open Interest, expressed in raw number of contracts.
  - *Market Prediction:* Provides the pure volume of newly added positions. Helpful for comparing positional aggression across different stocks regardless of their wildly different lot sizes.
- **Deliverable Ratio:** `(Turnover * Deliverable) / (60-Day Avg Turnover * 60-Day Avg Deliverable)`
  - *What it means:* Compares today's actual delivery buying to its historical 60-day average.
  - *Market Prediction:* A ratio `> 1.0` (especially `> 1.5`) is a massive footprint of institutional accumulation/distribution. A spike here often precedes extremely strong directional moves.
- **Future Cash Ratio:** `Future Turnover / Cash Turnover`
  - *What it means:* Measures the speculative trading interest (Futures) vs investment interest (Equities).
  - *Market Prediction:* Abnormally high speculative interest can signify excessive leverage, often leading to sharp short-covering or long-unwinding volatile moves.
- **Option Ratios (PE/CE):** 
  - *What it means:* The ratio of Traded Put Volume to Call Volume.
  - *Market Prediction:* This is a classic contrarian indicator. A very high PCR implies extreme retail bearishness, which often marks a market bottom (bullish reversal).

### Suggested Additional Improvements to Predict Markets

If you want to upgrade your algorithm to be even more predictive, consider calculating these new fields:

1. **VWAP-Close Delta (`(Close - VWAP) / VWAP * 100`):**
   - Comparing the Closing Price to the Volume Weighted Average Price reveals late-day institutional action. If `Close > VWAP`, it signifies strong last-hour buying pressure.
2. **Open Interest PCR (OI Put-Call Ratio):**
   - Right now, your script calculates *Volume* PE/CE ratio. Fetching the total outstanding *Open Interest* for Puts vs Calls across the nearest strikes offers a much stickier map of where major Option Writers (smart money) are sitting.
3. **Rollover Percentage:**
   - During the last week of the month, evaluating `Next Month OI / (Current OI + Next Month OI)` tracks how aggressively institutions are rolling their bets into the next month versus closing them out.
4. **Z-Score of Deliverable Volume:**
   - Instead of just a ratio, calculating the standard deviations (Z-score) of today's deliverable quantity against the 60-day rolling mean dynamically signals statistical anomalies in accumulation.
