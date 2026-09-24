#!/usr/bin/env python3
import os
import shutil
import subprocess  # nosec
import sys
from typing import List

import requests

# Color codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

def print_banner():
    print(f"\n{BOLD}ReadyTrader-Stocks Setup Wizard 🛡️{RESET}")
    print("-----------------------------------")
    print("This script will help you prepare your environment for AI-agentic trading.\n")

def check_env_file() -> bool:
    if os.path.exists(".env"):
        print(f"{GREEN}[✓]{RESET} .env file found.")
        return True
    else:
        print(f"{YELLOW}[?]{RESET} .env file missing.")
        choice = input("Do you want to create a .env from env.example now? (y/n): ")
        if choice.lower() == 'y':
            shutil.copy("env.example", ".env")
            print(f"{GREEN}[✓]{RESET} .env file created. Please open it and fill in your keys later.")
            return True
    return False

def check_dependencies() -> List[str]:
    print("\nChecking Python dependencies...")
    missing = []
    # Key dependencies to check
    deps = ["fastmcp", "yfinance", "pandas", "pandas_ta", "alpaca", "feedparser", "requests"]
    for dep in deps:
        try:
            __import__(dep)
            print(f"  {GREEN}[✓]{RESET} {dep}")
        except ImportError:
            print(f"  {RED}[✗]{RESET} {dep} (Missing)")
            missing.append(dep)
    return missing

def check_connectivity():
    print("\nChecking Network Connectivity...")
    targets = [
        ("Yahoo Finance (market data)", "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=1d&interval=1d"),
        ("Yahoo Finance RSS (news)", "https://finance.yahoo.com/news/rssindex"),
        ("MarketWatch RSS (news)", "https://www.marketwatch.com/rss/marketupdate"),
    ]
    
    for name, url in targets:
        try:
            res = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0 (ReadyTrader-Stocks setup)"})
            if res.status_code == 200:
                print(f"  {GREEN}[✓]{RESET} {name} reachable.")
            else:
                print(f"  {YELLOW}[?]{RESET} {name} returned status {res.status_code}.")
        except Exception as e:
            print(f"  {RED}[✗]{RESET} {name} unreachable: {str(e)}")

def check_keys():
    print("\nChecking Critical Keys in .env...")
    if not os.path.exists(".env"):
        return

    from dotenv import load_dotenv
    load_dotenv()
    
    # Same reading as the server (common/switches.py): only false/0/no/off leaves paper mode.
    paper = (os.getenv("PAPER_MODE") or "true").strip().lower() not in ("false", "0", "no", "off")
    print(f"  {GREEN}[✓]{RESET} PAPER_MODE={'true' if paper else 'false'}")
    # Brokerage keys are only needed for live trading (PAPER_MODE=false, LIVE_TRADING_ENABLED=true).
    for key in ("ALPACA_API_KEY", "ALPACA_API_SECRET", "TRADIER_ACCESS_TOKEN"):
        if os.getenv(key):
            print(f"  {GREEN}[✓]{RESET} {key} detected.")
        elif paper:
            print(f"  {YELLOW}[-]{RESET} {key} not set (only needed for live trading).")
        else:
            print(f"  {RED}[✗]{RESET} {key} is MISSING (live trading is configured).")

def main():
    print_banner()
    
    check_env_file()
    missing_deps = check_dependencies()
    
    if missing_deps:
        print(f"\n{YELLOW}Missing dependencies detected.{RESET}")
        choice = input("Would you like to install them now? (y/n): ")
        if choice.lower() == 'y':
            print("Installing...")
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]) # nosec
            print(f"{GREEN}Installation complete.{RESET}")
    
    check_connectivity()
    check_keys()
    
    print(f"\n{BOLD}Setup Scan Complete!{RESET}")
    print("Next steps:")
    print(f"1. Open {BOLD}.env{RESET}; paper mode needs no keys. For live trading see the README.")
    print(f"2. Read {BOLD}docs/SENTIMENT.md{RESET} for intelligence feed setup.")
    print(f"3. Run {BOLD}python app/main.py{RESET} to start the MCP server (your MCP client can launch it).\n")

if __name__ == "__main__":
    main()
