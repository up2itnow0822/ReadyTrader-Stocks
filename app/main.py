import sys
from pathlib import Path

if __package__ in (None, ""):
    # `python app/main.py` (README, Dockerfile, MCP client configs) puts app/ on sys.path, not the
    # repository root that the `app`, `core` and `marketdata` packages live in.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import FastMCP  # noqa: E402

from app.tools.intelligence import register_intelligence_tools  # noqa: E402
from app.tools.market import register_market_tools  # noqa: E402
from app.tools.research import register_research_tools  # noqa: E402
from app.tools.trading import register_trading_tools  # noqa: E402

# Initialize FastMCP server
mcp = FastMCP("ReadyTrader-Stocks")

# Register Tools
register_market_tools(mcp)
register_trading_tools(mcp)
register_intelligence_tools(mcp)
register_research_tools(mcp)

if __name__ == "__main__":
    mcp.run()
