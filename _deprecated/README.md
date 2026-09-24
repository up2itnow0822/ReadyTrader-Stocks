# _deprecated/

Files kept for history, not part of ReadyTrader-Stocks. Nothing here is built, tested or shipped
(`.dockerignore` excludes this folder).

- `sentinel/`, `docker-compose.sentinel.yml`: a transaction-signing service carried over from
  ReadyTrader-Crypto. It imports a `signing` package this repository does not have, so it cannot
  start, and a stocks server signs no transactions: brokerage orders use API keys.
