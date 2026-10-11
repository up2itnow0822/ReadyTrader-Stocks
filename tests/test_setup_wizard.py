"""tools/setup_wizard.py: no traceback without a terminal."""

import importlib.util
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("setup_wizard", ROOT / "tools" / "setup_wizard.py")
wizard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wizard)


def test_a_closed_stdin_is_no_answer_not_a_crash(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert wizard.check_env_file() is False
    assert "cp env.example .env" in capsys.readouterr().out
