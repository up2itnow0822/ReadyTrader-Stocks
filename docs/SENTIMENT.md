# Market Intelligence & Sentiment Guide (ReadyTrader-Stocks)

ReadyTrader-Stocks empowers AI agents with "Eyes" (intelligence) to navigate the stock market. This document explains how to configure and use the various sentiment and news feeds.

## 🌟 Overview of Sentiment Sources

| Source | Target | Cost | Required Credentials | 
| :--- | :--- | :--- | :--- |
| **RSS Market News** | General | Free | None (MarketWatch, Yahoo Finance) |
| **Fear & Greed Index** | Market | Free | None |
| **Reddit** | Social | Free | Client ID + Secret (/r/wallstreetbets) |
| **NewsAPI** | Financial | Free (Trial) | API Key (Bloomberg, Reuters) |

---

## 🛠️ Configuration Instructions

### 1. Free News & Sentiment
Work **out-of-the-box**. Agents use `fetch_rss_news` and `get_market_sentiment` without any keys.

### 2. Reddit Sentiment (High Alpha)
Great for detecting retail buzz and "meme stock" momentum.
1.  Go to [Reddit App Preferences](https://www.reddit.com/prefs/apps).
2.  Click "Create another app..." -> select **script**.
3.  Add credentials to `.env`:
    ```bash
    REDDIT_CLIENT_ID=your_id
    REDDIT_CLIENT_SECRET=your_secret
    ```

### 3. Financial News (Institutional)
For high-signal news from major financial outlets via NewsAPI.
1.  Get a key at [NewsAPI.org](https://newsapi.org/).
2.  Add to `.env`:
    ```bash
    NEWSAPI_KEY=your_key
    ```

---

## 🤖 Agent Tool Reference

- `fetch_rss_news(symbol="")`: Aggregates public RSS feeds. Best for general context.
- `get_market_sentiment()`: Returns the Stock Market Fear & Greed Index.
- `get_social_sentiment(symbol)`: Returns recent X and Reddit posts about a ticker **for you to read**. Returns text, not a score — see "The Falling Knife rule" below.
- `get_financial_news(symbol)`: Queries high-tier publications (Bloomberg, Reuters).

______________________________________________________________________

## The Falling Knife rule, and why this server does not score sentiment

`get_social_sentiment(symbol)` returns **posts, not a number**. That is a deliberate decision, and this section records the evidence behind it so it can be revisited rather than rediscovered.

### What was broken

`analyze_social_sentiment` added a flat `+0.2` for each configured source. The score therefore measured *how many API keys were set*, not what anyone was saying: a panicking feed and a euphoric feed both scored `+0.4`, and the only reachable values were `0.0`, `0.2` and `0.4`. The Risk Guardian's Falling Knife rule blocks a BUY below `-0.5`, so it could never fire. A second defect made this moot anyway — the order path passed a hardcoded `0.0`.

### What was tried

A deterministic replacement was built: VADER's rule engine (negation, intensifiers, capitals) over a market-only vocabulary instead of general-English sentiment, scoring the bull-bear spread over directional texts. The same design is in production in the crypto sibling of this repo, where it works.

It was then measured against simulated ticker searches written by models that had never seen its vocabulary, with the configuration frozen before scoring, and hardened through two rounds of adversarial review.

### What the measurement showed (equities)

Across three independently written corpora of 30 feeds each:

| corpus | crashes blocked | ordinary days falsely blocked |
| :-------------------------- | :-------------- | :---------------------------- |
| development (tuned against) | 4 of 8 | 1 of 22 |
| held out | 1 of 8 | 0 of 22 |
| written last, after hardening | 1 of 8 | 0 of 22 |

Roughly **one crash in eight**. Worse, adversarial probing found ordinary days it *does* block, in every configuration tried: a sector peer crashing while this stock shows relative strength, a broad market down day, and an earnings **beat** whose feed quotes business metrics ("net income fell 40%, operating income down 19%, but shares up 6%"). Those are common days, and they are exactly the days an agent asks for sentiment.

The root cause is not tuning. Realistic equity crash feeds are written in **facts and market structure**, not in crash vocabulary:

> "pulls FY guidance entirely" · "will restate FY24" · "immediate departure of the CEO" · "removed from the index at the rebalance" · "no bid depth under 15" · "a five dollar air pocket below here"

No word list reads any of that. The crypto sibling works because crypto feeds genuinely do say "bloodbath" and "rekt", and rarely discuss another asset's income statement. Equity feeds are full of business metrics, peer comparisons and acronyms — precisely what breaks a lexicon scorer. Every guard added to fix one false positive (non-price nouns, non-ticker acronyms) was an unbounded list that opened others.

A gate that catches one crash in eight and blocks good buys on peer news is net negative, so it was not shipped.

### What ships instead

- **The order path is no longer a bypass.** It reads the same sentiment value as the validation tool, and now passes daily loss and drawdown, which it never did — so those two rules apply to real orders for the first time.
- **Nothing fabricates a number.** The cache stores how much text was fetched, never a score.
- **The absence of a measurement is visible.** Every verdict carries a `sentiment` block whose `source` is `unmeasured` or `agent_supplied` — never a measurement by this server — plus a `hint` saying what to do about it.
- **The agent can supply its own reading.** `validate_trade_risk(..., sentiment_score=...)` and every order entry point accept a score on `[-1, +1]`. You are an LLM reading the actual posts, which is a far better judge of them than any word list, and the response records that the judgement was yours.

### The durable fix (done)

The Falling Knife rule is now also driven by **price**, which needs no sentiment at all. Every BUY now reads the stock's recent daily closes and is refused while it is still falling after a 15%+ drop. The thresholds were chosen on historical data and tested on instruments the choice never saw; see [FALLING_KNIFE.md](FALLING_KNIFE.md). Volume was tested as an extra condition (a 2x volume spike) and barely changed the result, so the shipped rule uses closes only. The sentiment rule above still applies on top, when you supply a reading.

The benchmark corpora used above are simulations, not market data. They are preserved outside the repo so that any future scorer can be compared against the same feeds.
