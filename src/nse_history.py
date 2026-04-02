"""Implements functionality to download historical stock, index and

derivatives data from NSE and
NSEIndices website
"""

import itertools
from io import StringIO
from urllib.parse import urljoin
from jugaad_data import util as ut
import pandas as pd
from requests import Session

APP_NAME = 'nsehistory'


class NSEHistory:

  def __init__(self):

    self.headers = {
        'Host': 'www.nseindia.com',
        'Referer': 'https://www.nseindia.com/get-quotes/equity?symbol=SBIN',
        'X-Requested-With': 'XMLHttpRequest',
        'pragma': 'no-cache',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            ' (KHTML, like Gecko) Chrome/80.0.3987.132 Safari/537.36'
        ),
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
    }
    self.path = '/api/NextApi/apiClient/GetQuoteApi'
    self.base_url = 'https://www.nseindia.com'
    self.cache_dir = '.cache'
    self.workers = 2
    self.use_threads = True
    self.show_progress = False

    self.s = Session()
    self.s.headers.update(self.headers)
    self.ssl_verify = True

  def _get(self, params):
    url = urljoin(self.base_url, self.path)
    self.r = self.s.get(url, params=params, verify=self.ssl_verify)
    return self.r

  @ut.cached(APP_NAME + '-stock')
  def _stock(self, symbol, from_date, to_date, series='EQ'):
    params = {
        'functionName': 'getHistoricalTradeData',
        'symbol': symbol,
        'fromDate': from_date.strftime('%d-%m-%Y'),
        'toDate': to_date.strftime('%d-%m-%Y'),
        'series': series,
    }
    self.r = self._get(params)
    j = self.r.json()
    return j

  @ut.cached(APP_NAME + '-derivatives')
  def _derivatives(
      self,
      symbol,
      from_date,
      to_date,
      expiry_date,
      instrument_type,
  ):

    params = {
        'functionName': 'getDerivativesHistoricalData',
        'symbol': symbol,
        'fromDate': from_date.strftime('%d-%m-%Y'),
        'toDate': to_date.strftime('%d-%m-%Y'),
        'expiryDate': expiry_date.strftime('%d-%b-%Y').upper(),
        'instrumentType': instrument_type,
    }

    self.r = self._get(params)
    j = self.r.json()
    return j

  @ut.cached(APP_NAME + '-option_chain')
  def _option_chain(self, symbol, expiry_date, today_str=None):
    params = {
        'functionName': 'getOptionChainData',
        'symbol': symbol,
        'params': 'expiryDate=' + expiry_date.strftime('%d-%b-%Y').upper(),
    }
    self.r = self._get(
        params,
    )
    j = self.r.json()
    return j

  @ut.cached(APP_NAME + '-deliverables')
  def _deliverables_raw(self, symbol, from_date, to_date):
      d_url = f"https://www.nseindia.com/api/historicalOR/generateSecurityWiseHistoricalData?from={from_date.strftime('%d-%m-%Y')}&to={to_date.strftime('%d-%m-%Y')}&symbol={symbol}&type=priceVolumeDeliverable&series=ALL&csv=true"
      self.s.headers.update({"Referer": "https://www.nseindia.com/report-detail/eq_security"})
      return self.s.get(d_url, timeout=10).text

  def _deliverables(self, symbol, from_date, to_date, dates_series):
    try:
      csv_text = self._deliverables_raw(symbol, from_date, to_date)
      
      if csv_text and '"Date' in csv_text:
          dly_raw = pd.read_csv(StringIO(csv_text))
          dly_raw.columns = [c.strip() for c in dly_raw.columns]
          dly_raw['join_date'] = pd.to_datetime(dly_raw['Date']).dt.date
          
          # Map percentage metric 
          join_dates = pd.to_datetime(dates_series).dt.date
          dmap = dly_raw.set_index('join_date')['% Dly Qt to Traded Qty'].to_dict()
          deliverables = join_dates.map(dmap)
          
          # Clean string formats
          deliverables = deliverables.replace({',': '', '-': '0'}, regex=True)
          return pd.to_numeric(deliverables, errors='coerce').fillna(0.0)
    except Exception as e:
        print(f"Failed to fetch deliverables for {symbol}: {e}")
    return 0.0

  def stock_raw(self, symbol, from_date, to_date, series='EQ'):
    date_ranges = ut.break_dates(from_date, to_date)
    params = [(symbol, x[0], x[1], series) for x in reversed(date_ranges)]
    chunks = ut.pool(self._stock, params, max_workers=self.workers)

    return list(itertools.chain.from_iterable(chunks))

  def derivatives_raw(
      self,
      symbol,
      from_date,
      to_date,
      expiry_date,
      instrument_type,
  ):
    date_ranges = ut.break_dates(from_date, to_date)
    params = [
        (
            symbol,
            x[0],
            x[1],
            expiry_date,
            instrument_type,
        )
        for x in reversed(date_ranges)
    ]
    chunks = ut.pool(self._derivatives, params, max_workers=self.workers)
    return list(itertools.chain.from_iterable(chunks))

  def oi_chain_raw(self, symbol, expiry_date=None, today_str=None):
    payload = self._option_chain(symbol, expiry_date, today_str=today_str)
    return payload.get('data', [])


def stock_df(h, symbol, from_date, to_date, series='EQ'):
  stock_select_headers = [
      'mtimestamp',
      'chSeries',
      'chOpeningPrice',
      'chTradeHighPrice',
      'chTradeLowPrice',
      'chPreviousClsPrice',
      'chLastTradedPrice',
      'chClosingPrice',
      'vwap',
      'ch52WeekHighPrice',
      'ch52WeekLowPrice',
      'chTotTradedQty',
      'chTotTradedVal',
      'chTotalTrades',
      'chSymbol',
  ]
  stock_final_headers = [
      'DATE',
      'SERIES',
      'OPEN',
      'HIGH',
      'LOW',
      'PREV. CLOSE',
      'LTP',
      'CLOSE',
      'VWAP',
      '52W H',
      '52W L',
      'VOLUME',
      'VALUE',
      'NO OF TRADES',
      'SYMBOL',
  ]
  stock_dtypes = [
      ut.np_date,
      str,
      ut.np_float,
      ut.np_float,
      ut.np_float,
      ut.np_float,
      ut.np_float,
      ut.np_float,
      ut.np_float,
      ut.np_float,
      ut.np_float,
      ut.np_int,
      ut.np_float,
      ut.np_int,
      str,
  ]
  stock_raw = h.stock_raw
  raw = stock_raw(symbol, from_date, to_date, series)
  df = pd.DataFrame(raw)[stock_select_headers]
  df.columns = stock_final_headers
  for i, header in enumerate(stock_final_headers):
    df[header] = df[header].apply(stock_dtypes[i])

  # Natively fetch deliverables via CSV endpoint helper method
  df['DELIVERABLE'] = h._deliverables(symbol, from_date, to_date, df['DATE'])

  df['DELIVERABLE'] = df['DELIVERABLE'].apply(ut.np_float)
  df = df.sort_values(by='DATE')
  return df


def derivatives_df(
    h,
    symbol,
    from_date,
    to_date,
    expiry_date,
    instrument_type='FUTSTK',
):
  futures_select_headers = [
      'FH_TIMESTAMP',
      'FH_EXPIRY_DT',
      'FH_OPENING_PRICE',
      'FH_TRADE_HIGH_PRICE',
      'FH_TRADE_LOW_PRICE',
      'FH_CLOSING_PRICE',
      'FH_LAST_TRADED_PRICE',
      'FH_SETTLE_PRICE',
      'FH_TOT_TRADED_QTY',
      'FH_MARKET_LOT',
      'FH_TOT_TRADED_VAL',
      'FH_OPEN_INT',
      'FH_CHANGE_IN_OI',
      'FH_SYMBOL',
  ]
  futures_final_headers = [
      'DATE',
      'EXPIRY',
      'OPEN',
      'HIGH',
      'LOW',
      'CLOSE',
      'LTP',
      'SETTLE PRICE',
      'TOTAL TRADED QUANTITY',
      'MARKET LOT',
      'PREMIUM VALUE',
      'OPEN INTEREST',
      'CHANGE IN OI',
      'SYMBOL',
  ]
  derivatives_raw = h.derivatives_raw
  raw = derivatives_raw(
      symbol,
      from_date,
      to_date,
      expiry_date,
      instrument_type,
  )
  futures_dtype = [
      ut.np_date,
      ut.np_date,
      ut.np_float,
      ut.np_float,
      ut.np_float,
      ut.np_float,
      ut.np_float,
      ut.np_float,
      ut.np_int,
      ut.np_int,
      ut.np_float,
      ut.np_float,
      ut.np_float,
      str,
  ]

  final_headers = futures_final_headers
  select_headers = futures_select_headers
  dtypes = futures_dtype
  df = pd.DataFrame(raw)[select_headers]
  df.columns = final_headers
  for i, h in enumerate(final_headers):
    df[h] = df[h].apply(dtypes[i])
  return df


def oi_chain_df(h, symbol, expiry_date):
  col_names = [
      'Calls Change in OI',
      'Puts Change in OI',
      'Calls OI',
      'Puts OI',
      'Calls Last Price',
      'Puts Last Price',
  ]
  oi_data = pd.DataFrame(columns=col_names)

  from datetime import date
  today_str = date.today().strftime('%Y-%m-%d')
  data = h.oi_chain_raw(symbol, expiry_date, today_str=today_str)
  for item in data:
    oi_row = {}
    try:
      if 'CE' in item and item['CE']:
        ce = item['CE']
        oi_row['CALLS OI'] = float(ce.get('openInterest', 0))
        oi_row['CALLS CHANGE IN OI'] = float(ce.get('changeinOpenInterest', 0))
        oi_row['CALLS LAST PRICE'] = float(ce.get('lastPrice', 0))
    except (KeyError, ValueError, TypeError):
      pass
    try:
      if 'PE' in item and item['PE']:
        pe = item['PE']
        oi_row['PUTS OI'] = float(pe.get('openInterest', 0))
        oi_row['PUTS CHANGE IN OI'] = float(pe.get('changeinOpenInterest', 0))
        oi_row['PUTS LAST PRICE'] = float(pe.get('lastPrice', 0))
    except (KeyError, ValueError, TypeError):
      pass
    oi_data = pd.concat([oi_data, pd.DataFrame([oi_row])], ignore_index=True)
  return oi_data
