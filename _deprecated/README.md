# _deprecated/

Files kept for history, not part of ReadyTrader-Stocks. Nothing here is built, tested or shipped
(`.dockerignore` excludes this folder).

- `sentinel/`, `docker-compose.sentinel.yml`: a transaction-signing service carried over from
  ReadyTrader-Crypto. It imports a `signing` package this repository does not have, so it cannot
  start, and a stocks server signs no transactions: brokerage orders use API keys.
- `configs/agent_zero.mcp.yaml`: an `mcp_servers:` YAML block for an `agent.yaml` that current Agent
  Zero (v2.13) does not read for MCP servers. Replaced by `configs/agent_zero.mcp.json`, the JSON that
  goes in Agent Zero's Settings → MCP/A2A → External MCP Servers (see the README's Integration Guide).
