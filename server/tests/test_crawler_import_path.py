"""PluginMarketWorker import path regression tests."""
import subprocess
import sys
from pathlib import Path


def test_plugin_market_worker_imports_agentctl_package_from_server_cwd():
    root = Path(__file__).resolve().parent.parent.parent
    code = "import PluginMarketWorker; from agentctl.lib.plugin_builder import PluginBuilder; print(PluginBuilder.__name__)"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root / "server",
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "PluginBuilder" in result.stdout
