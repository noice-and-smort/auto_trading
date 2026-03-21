import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
import logging
import warnings
from dateutil.relativedelta import TU, relativedelta
from nse_history import NSEHistory, derivatives_df, oi_chain_df, stock_df
import numpy as np
import pandas as pd
from send_email import send_email

logger = logging.getLogger(__name__)


def get_option_data(h, symbol, expiry_date="latest"):
  if expiry_date == "latest":
    expiry_date = get_expiry_with_offset(date.today())
  
  retries = 0
  while retries < 7:
    try:
      oi_data = oi_chain_df(h, symbol, expiry_date)
      if oi_data.empty:
        expiry_date = expiry_date - relativedelta(days=1)
        retries += 1
        continue
        
      options_dict = {}
      options_dict["F1"] = (
          oi_data["PUTS CHANGE IN OI"].sum() / oi_data["CALLS CHANGE IN OI"].sum()
      )
      options_dict["F2"] = oi_data["PUTS OI"].dot(
          oi_data["PUTS LAST PRICE"]
      ) / oi_data["CALLS OI"].dot(oi_data["CALLS LAST PRICE"])
      return options_dict
    except (ZeroDivisionError, KeyError):
      return {"F1": 0, "F2": 0}

  return {"F1": 0, "F2": 0}


def rsi(close, periods=14):
  close_delta = close.diff()
  up = close_delta.clip(lower=0)
  down = -1 * close_delta.clip(upper=0)
  ma_up = up.rolling(window=periods).mean()
  ma_down = down.rolling(window=periods).mean()
  old = True
  for i in range(len(close)):
    if ~np.isnan(ma_up[i]) and ~np.isnan(ma_down[i]):
      old = False
    if not old:
      if ~np.isnan(ma_up[i - 1]) and ~np.isnan(ma_down[i - 1]):
        ma_up[i] = (ma_up[i - 1] * (periods - 1) + up[i]) / periods
        ma_down[i] = (ma_down[i - 1] * (periods - 1) + down[i]) / periods

  rsi = ma_up / ma_down
  rsi = 100 - (100 / (1 + rsi))
  return rsi


def get_RSI_ratio(close, RSI):
  close_shifted = close.shift(1)
  RSI_shifted = RSI.shift(1)

  close_diff = close - close_shifted
  RSI_diff = RSI - RSI_shifted
  ratio = close_diff / RSI_diff
  return ratio


def get_expiry_with_offset(dt, offset=0):
  expiry_dates = []
  for i in range(offset + 3):
    expiry_dates.append(dt + relativedelta(day=31, months=i, weekday=TU(-1)))
  if expiry_dates[0] >= dt:
    return expiry_dates[offset]
  else:
    return expiry_dates[offset + 1]


def get_date_splits(dt_start, dt_end):
  splits = []
  curr_date = dt_start
  while curr_date <= dt_end:
    if get_expiry_with_offset(curr_date) <= dt_end:
      expiry_date = get_expiry_with_offset(curr_date)
      splits.append([curr_date, expiry_date])
      curr_date = expiry_date + timedelta(days=1)
    else:
      splits.append([curr_date, dt_end])
      break
  return splits


def get_future_data_for_date(h, stock, start_date, end_date, expiry_date):
  try:
    future_data_for_date = derivatives_df(
        h,
        symbol=stock,
        from_date=start_date,
        to_date=end_date,
        expiry_date=expiry_date,
    )
  except KeyError:
    future_data_for_date = pd.DataFrame()
  while future_data_for_date.empty and expiry_date > start_date:
    expiry_date = expiry_date - relativedelta(days=1)
    try:
      future_data_for_date = derivatives_df(
          h,
          symbol=stock,
          from_date=start_date,
          to_date=end_date,
          expiry_date=expiry_date,
      )
    except KeyError:
      future_data_for_date = pd.DataFrame()
  return format_df(future_data_for_date, True)


def get_future_data(h, stock, start_date, end_date, offset):
  splits = get_date_splits(start_date, end_date)
  future_data = [
      get_future_data_for_date(
          h, stock, d[0], d[1], expiry_date=get_expiry_with_offset(d[0], offset)
      )
      for d in splits
  ]
  future_data_concat = pd.concat(future_data)
  future_data_concat = future_data_concat[
      ~future_data_concat.index.duplicated(keep="first")
  ]
  return future_data_concat


def format_df(df, reverse=False):
  if df.empty:
    return df
  df["Date"] = pd.to_datetime(df["DATE"]).dt.date
  df = df.set_index("Date")
  if reverse:
    df = df.iloc[::-1]
  return df


def run_once(h, stock, time_period_in_days, rsi_window_length):
  # get last thursday
  d = datetime.now()
  date_today = date(d.year, d.month, d.day)
  heading = False
  stock_data = []

  cash_data = stock_df(
      h,
      symbol=stock,
      from_date=date_today - timedelta(days=time_period_in_days),
      to_date=date_today,
      series="EQ",
  )
  cash_data = format_df(cash_data)
  future_data_current = get_future_data(
      h, stock, date_today - timedelta(days=time_period_in_days), date_today, 0
  )
  future_data_next = get_future_data(
      h, stock, date_today - timedelta(days=time_period_in_days), date_today, 1
  )
  average_turnrover = cash_data["VALUE"].mean()
  average_deliverable = cash_data["DELIVERABLE"].mean() / 100
  lot_size = future_data_current["MARKET LOT"].astype("float64")
  combined_data = pd.DataFrame()
  combined_data["Symbol"] = cash_data["SYMBOL"]
  combined_data["Deliverble"] = cash_data["DELIVERABLE"].astype("float64") / 100
  combined_data["Average Price"] = cash_data["VWAP"].astype("float64")
  combined_data["High"] = cash_data["HIGH"].astype("float64")
  combined_data["Low"] = cash_data["LOW"].astype("float64")
  combined_data["Close"] = cash_data["CLOSE"].astype("float64")
  combined_data["Last"] = cash_data["LTP"].astype("float64")
  combined_data["Prev Close"] = cash_data["PREV. CLOSE"].astype("float64")
  combined_data["Turnover"] = cash_data["VALUE"].astype("float64")

  combined_data["Settle Price"] = future_data_current["SETTLE PRICE"].astype(
      "float64"
  )
  combined_data["Future Turnover"] = future_data_current[
      "PREMIUM VALUE"
  ].astype("float64")
  combined_data["Number of Contracts"] = (
      future_data_current["TOTAL TRADED QUANTITY"].astype("float64") / lot_size
  )
  combined_data["Open Interest"] = future_data_current["OPEN INTEREST"].astype(
      "float64"
  )
  combined_data["Change in OI"] = future_data_current["CHANGE IN OI"].astype(
      "float64"
  )
  combined_data["Change in OI Next"] = future_data_next["CHANGE IN OI"].astype(
      "float64"
  )
  combined_data["Open Interest Next"] = future_data_next[
      "OPEN INTEREST"
  ].astype("float64")
  combined_data["Number of Contracts Next"] = (
      future_data_next["TOTAL TRADED QUANTITY"].astype("float64") / lot_size
  )

  combined_data["Average Turnover"] = [
      average_turnrover for i in range(len(combined_data))
  ]
  combined_data["Average Deliverble"] = [
      average_deliverable for i in range(len(combined_data))
  ]

  combined_data["F1"] = (combined_data["Change in OI"] * 100) / combined_data[
      "Open Interest"
  ]
  combined_data["F7"] = combined_data["Number of Contracts"] / (
      combined_data["Change in OI"] / lot_size
  )
  combined_data["Future Cash Ratio"] = (
      combined_data["Future Turnover"] / combined_data["Turnover"]
  )
  combined_data["Deliverble Ratio"] = (
      combined_data["Turnover"] * combined_data["Deliverble"]
  ) / (average_turnrover * average_deliverable)
  combined_data["F8"] = (
      (combined_data["Change in OI"] + combined_data["Change in OI Next"]) * 100
  ) / (combined_data["Open Interest"] + combined_data["Open Interest Next"])
  combined_data["F9"] = (
      combined_data["Number of Contracts"]
      + combined_data["Number of Contracts Next"]
  ) / (
      (combined_data["Change in OI"] + combined_data["Change in OI Next"])
      / lot_size
  )

  combined_data["%Price Change"] = (
      np.log(combined_data["Close"] / combined_data["Prev Close"]) * 100
  )

  combined_data["RSI"] = rsi(combined_data["Close"], rsi_window_length)
  combined_data["RSI Ratio"] = get_RSI_ratio(
      combined_data["Close"], combined_data["RSI"]
  )

  columnsTitles = [
      "Symbol",
      "Average Price",
      "High",
      "Low",
      "Close",
      "Last",
      "Prev Close",
      "Turnover",
      "Deliverble",
      "Average Turnover",
      "Average Deliverble",
      "Settle Price",
      "Future Turnover",
      "F1",
      "F7",
      "Future Cash Ratio",
      "Deliverble Ratio",
      "Number of Contracts",
      "Open Interest",
      "Change in OI",
      "F8",
      "F9",
      "%Price Change",
      "RSI",
      "RSI Ratio",
  ]
  combined_data = combined_data.reindex(columns=columnsTitles)

  if not heading:
    stock_data.append(["Date"] + list(combined_data.columns))
    heading = True

  i = 0
  for row in combined_data.values.tolist():
    row_list = [str(combined_data.index[i])]
    i += 1
    for cell in row:
      if type(cell) != str:
        row_list.append(str(round(cell, 2)))
      else:
        row_list.append(cell)
    stock_data.append(row_list)

  avg_list = ["Average"] + [
      str(round(combined_data.iloc[:, i].mean(), 2))
      if type(combined_data.iloc[0, i]) != str
      else ""
      for i in range(combined_data.shape[1])
  ]

  options_data = get_option_data(h, stock)
  options_list = [
      "Option Ratios (PE/CE)",
      str(round(options_data["F1"], 2)),
      str(round(options_data["F2"], 2)),
  ]

  stock_data.append(avg_list)
  stock_data.append(options_list)

  if options_data == {"F1": 0, "F2": 0}:
    print(stock + " " + "No Option data")
  else:
    print(stock)

  return (stock, stock_data)


def write_to_file(stock_data_list, file_name):
  # to write data
  with open(file_name, "w") as f:
    stock_data_list.sort(key=lambda x: x[0])
    for stock_name, stock_data in stock_data_list:
      if stock_data:
        for row in stock_data:
          f.write(",".join(row))
          f.write("\n")
        f.write("\n\n")


def run(h, stock, time_period_in_days=60, rsi_window_length=14):
  try:
    return run_once(h, stock, time_period_in_days, rsi_window_length)
  except Exception as e:
    logger.error(f"Error processing stock {stock}: {e}", exc_info=True)
    return (stock, None)


def bulk_run():
  # get stocks
  h = NSEHistory()
  stocks = []
  with open("stocks") as f:
    for line in f:
      if line.strip():
        stocks.append(line.strip())
  
  with ThreadPoolExecutor(max_workers=10) as executor:
      # Map returns results in the order of input iterable
      results = executor.map(lambda stock: run(h, stock), stocks)
      
  return list(results)


if __name__ == "__main__":
  warnings.filterwarnings("ignore")
  d = datetime.now()
  ds = d.strftime("%Y.%m.%d")
  out_file = "output/combined_{}.csv".format(ds)
  stock_data_list = bulk_run()
  write_to_file(stock_data_list, out_file)
  email_on = False
  if email_on:
    send_email(out_file, ds)
