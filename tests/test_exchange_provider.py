from unittest.mock import MagicMock, patch

import pandas as pd

from marketdata.exchange_provider import ExchangeProvider


def test_ticker_cache_hits():
    # Mocking yfinance since we don't pass exchanges anymore
    with patch("yfinance.Ticker") as mock_ticker:
        mock_inst = MagicMock()
        mock_inst.history.return_value = pd.DataFrame({
            "Open": [100.0], "High": [110.0], "Low": [90.0], "Close": [105.0], "Volume": [1000.0]
        }, index=[pd.Timestamp.now()])
        mock_ticker.return_value = mock_inst
        
        provider = ExchangeProvider()
        ticker = provider.fetch_ticker("AAPL")
        assert ticker["last"] == 105.0
        
        # Second call should hit cache (mock_ticker called once)
        provider.fetch_ticker("AAPL")
        assert mock_ticker.call_count == 1

def test_fetch_ohlcv_formatting():
    with patch("yfinance.Ticker") as mock_ticker:
        mock_inst = MagicMock()
        mock_inst.history.return_value = pd.DataFrame({
            "Open": [100.0], "High": [110.0], "Low": [90.0], "Close": [105.0], "Volume": [1000.0]
        }, index=[pd.Timestamp.now()])
        mock_ticker.return_value = mock_inst
        
        provider = ExchangeProvider()
        ohlcv = provider.fetch_ohlcv("AAPL", timeframe="1h", limit=1)
        assert len(ohlcv) == 1
        assert len(ohlcv[0]) == 6 # [ts, o, h, l, c, v]
        assert ohlcv[0][4] == 105.0


def _frame():
    return pd.DataFrame(
        {"Open": [100.0], "High": [110.0], "Low": [90.0], "Close": [105.0], "Volume": [1000.0]},
        index=[pd.Timestamp.now()],
    )


def test_a_dotted_share_class_is_retried_in_yahoo_form():
    """Brokers write BRK.B, Yahoo writes BRK-B. Without the retry every data tool - and the Falling
    Knife check, which blocks live BUYs when it cannot read bars - failed for share classes."""
    asked = []

    def ticker(sym):
        asked.append(sym)
        inst = MagicMock()
        inst.history.return_value = _frame() if sym == "BRK-B" else pd.DataFrame()
        return inst

    with patch("yfinance.Ticker", side_effect=ticker):
        provider = ExchangeProvider()
        assert provider.fetch_ohlcv("BRK.B", timeframe="1d", limit=1)[0][4] == 105.0
        assert provider.fetch_ticker("brk.b")["last"] == 105.0
    assert asked == ["BRK.B", "BRK-B", "BRK.B", "BRK-B"]


def test_a_symbol_that_resolves_is_not_rewritten():
    """Exchange suffixes Yahoo writes with a dot (SHOP.TO) must not be turned into dashes."""
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = _frame()
        ExchangeProvider().fetch_ohlcv("SHOP.TO", timeframe="1d", limit=1)
    assert [c.args[0] for c in mock_ticker.call_args_list] == ["SHOP.TO"]
