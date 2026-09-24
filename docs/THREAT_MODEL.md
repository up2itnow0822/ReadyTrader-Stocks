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
    - **Execution Approval Mode**: Set `EXECUTION_APPROVAL_MODE=approve_each` to require manual human confirmation for every trade.
    - **Position size**: the Risk Guardian refuses any order over 5% of the account's equity, valued at the latest price, and every BUY after a 5% daily loss or a 10% drawdown.
    - **Falling Knife**: BUYs into a stock still falling after a 15% drop are refused (`docs/FALLING_KNIFE.md`).
    - **Policy limits**: `MAX_ORDER_AMOUNT` caps shares per live order; an unreadable value refuses every live order.
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
5.  **Local API only**: keep the API server on `127.0.0.1` (the default); it has no authentication beyond each proposal's `confirm_token`, and browsers other than the dashboard are refused (`API_CORS_ORIGINS`).
