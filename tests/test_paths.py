"""The server's files stay with the install, whatever working directory the MCP client uses."""

import os
import subprocess  # nosec B404 - runs this repo's own interpreter on a fixed script
import sys
from pathlib import Path

from common.paths import REPO_ROOT, data_path, ensure_parent

ROOT = Path(__file__).resolve().parent.parent


def test_data_files_default_to_the_repo_data_folder(monkeypatch):
    monkeypatch.delenv("READYTRADER_DATA_DIR", raising=False)
    assert REPO_ROOT == ROOT
    assert data_path("paper.db") == str(ROOT / "data" / "paper.db")


def test_the_data_folder_can_be_moved(monkeypatch, tmp_path):
    monkeypatch.setenv("READYTRADER_DATA_DIR", str(tmp_path / "state"))
    assert data_path("paper.db") == str(tmp_path / "state" / "paper.db")


def test_a_bare_file_name_needs_no_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert ensure_parent("execution.db") == "execution.db"


def test_every_store_ignores_the_working_directory(tmp_path):
    """Build each store from an unrelated working directory; none may write there."""
    state = tmp_path / "state"
    elsewhere = tmp_path / "client-cwd"
    elsewhere.mkdir()
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]);"
        "from core.paper import PaperTradingEngine; from intelligence.insights import InsightStore;"
        "from strategy.marketplace import StrategyRegistry; from execution.store import ExecutionStore;"
        "from app.core.compliance import ComplianceLedger;"
        "e = PaperTradingEngine(); e.deposit('u', 'USD', 1.0); InsightStore(); StrategyRegistry();"
        "ComplianceLedger().record_event('probe', {});"
        "print(e.db_path); print(ExecutionStore()._db_path())"
    )
    env = {k: v for k, v in os.environ.items() if not k.endswith("_DB_PATH")}
    env["READYTRADER_DATA_DIR"] = str(state)
    out = subprocess.run(  # nosec B603 - fixed argv, no shell
        [sys.executable, "-W", "ignore", "-c", code, str(ROOT)],
        cwd=elsewhere,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert out.strip().splitlines()[-2:] == [str(state / "paper.db"), str(state / "execution.db")]
    assert list(elsewhere.iterdir()) == []
    assert {"paper.db", "insights.db", "strategies.db", "compliance_audit.log"} <= {
        p.name for p in state.iterdir()
    }
