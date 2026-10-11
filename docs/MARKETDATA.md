# Market Data (ReadyTrader-Stocks)

## Where prices come from

Every price and candle the server uses comes from **yfinance** (Yahoo), through
`marketdata/exchange_provider.py`:

- `get_stock_price(symbol)` and `get_multiple_prices(symbols)`: the latest quote (`last`, with the
  day's open/high/low/volume), cached for `TICKER_CACHE_TTL_SEC` (5 s).
- `fetch_ohlcv(symbol, timeframe, limit)`: candles with ISO timestamps, cached for
  `OHLCV_CACHE_TTL_SEC` (60 s, never past the next daily boundary).
- The Risk Guardian values orders at the latest price, and the Falling Knife check reads the last
  40 daily bars (`docs/FALLING_KNIFE.md`); paper orders fill at the latest price.

No brokerage key is needed for market data. Yahoo's data is delayed for some exchanges and is
rate-limited; when it cannot be read the tools answer `market_data_error` / `history_error`, and
a live BUY is refused rather than priced on a guess.

## Not exposed in this release

The repository contains a `MarketDataBus` (freshness scoring, ingest, plugins) and an Alpaca
websocket stream manager (`marketdata/ws_streams.py`), but no tool starts a stream or reads the
bus, so they do not affect any answer. The API server's `/ws` endpoint is wired to the stream
store and stays silent until a stream is started.
