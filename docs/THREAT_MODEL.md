# ReadyTrader-Stocks Threat Model

This document is an operator-focused threat model for ReadyTrader-Stocks when configured for **live trading** (`PAPER_MODE=false`).

## 🌟 Security Philosophy
ReadyTrader-Stocks is a **Safety-First Bridge**. It is designed to minimize "fat finger" errors and limit the damage a compromised AI agent (or logic error) can do.

---

## 🚫 1. Brokerage API Key Compromise
- **Threat**: An attacker gains access to your `.env` file containing `ALPACA_API_KEY` or `TRADIER_ACCESS_TOKEN`.
- **Mitigation**:
    - Use environment-specific keys with restricted permissions (e.g., Trading only, no Withdrawals).
    - Set the live policy limits (`MAX_ORDER_AMOUNT`, `ALLOW_TICKERS`, `ALLOW_BROKERAGES`; enforced in `core/policy.py`).
    - Run ReadyTrader-Stocks in a secured container or isolated environment.

## 🚫 2. Rogue Agent / "Fat Finger" Trades
- **Threat**: The AI agent attempts to buy a massive amount of a volatile stock or enters a trade with an incorrect price.
- **Mitigation**:
    - **Execution Approval Mode**: Set `EXECUTION_APPROVAL_MODE=approve_each` to make every order a proposal. The proposal's `confirm_token` goes to the agent, so it alone does not prove a person approved: with `API_OPERATOR_TOKEN` set on the API server, approvals need that operator secret too, and a live proposal cannot be approved without it.
    - **Position size**: the Risk Guardian refuses any order that adds exposure worth over 5% of the account's equity (valued at the latest market price, never at a price the order carries; without a market price an order that adds exposure is refused), and, on the paper account, every order that adds exposure after a 5% daily loss or a 10% drawdown (deposits neither count as gains nor end a halt); selling out of a position stays possible. Live orders report the two loss rules in `inactive_rules`: the brokerage account has no loss history here.
    - **Mode**: a proposal made in paper mode is never executed live (and the reverse).
    - **Falling Knife**: BUYs into a stock still falling after a 15% drop are refused (`docs/FALLING_KNIFE.md`).
    - **Policy limits**: `MAX_ORDER_AMOUNT` caps shares per live order; an unreadable value refuses every live order.
    - **Orders fill when checked**: the Risk Guardian judges an order against the market and the positions at the moment it is placed, so an Alpaca order fills now or not at all: it is sent only while the market is open (else `market_closed`), as `IOC` (a fractional market order as `DAY`; a fractional limit is refused). A resting order could fill later, past every check and the kill switch (a BUY limit under the market fills during the fall the Falling Knife rule guards against). At the other brokerages a limit order can rest; open orders are never counted as exposure.
    - **Kill switch**: `TRADING_HALTED` refuses every live order and approval, closing orders included; flatten and cancel at the brokerage.
    - Not active in this release: the price-collar and Pattern Day Trader rules in `core/risk.py` are never given the inputs they need, so they never fire. Use `approve_each` and `MAX_ORDER_AMOUNT` for fat-finger protection.

## 🚫 3. Prompt Injection / Social Engineering
- **Threat**: A user convinces the AI agent to bypass safety rules or sell positions maliciously.
- **Mitigation**:
    - The **Risk Guardian** is hard-coded in Python and cannot be bypassed by prompt-level instructions.
    - Every order tool runs the same Risk Guardian check as `validate_trade_risk` before anything executes, and again when an `approve_each` proposal is approved.
    - News and social posts returned to the agent are untrusted text; the server never acts on them.

---

## 🔒 Best Practices
1.  **Never** reuse API keys across multiple apps.
2.  **Enable MFA** on your brokerage account for any manual actions.
3.  **Audit Logs**: Regularly review `data/compliance_audit.log` (one JSON line per order request) for unexpected trade payloads.
4.  **Paper First**: Always run a strategy in `PAPER_MODE=true` for at least 48 hours before enabling live trading, then on the brokerage's paper account or sandbox (`ALPACA_PAPER` / `TRADIER_SANDBOX`, both on by default).
5.  **Local API only**: keep the API server on `127.0.0.1` (the default) and set `API_OPERATOR_TOKEN` for it (not for the MCP server): without it the API has no authentication beyond each proposal's `confirm_token`, which the agent holds. Browsers other than the dashboard are refused (`API_CORS_ORIGINS`).
