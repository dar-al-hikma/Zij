"""The sky host's Node leg (tests/js/sky_host.test.mjs), beside pytest. Node stands on every
machine the suite is expected to run on, so its absence fails rather than skips."""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_the_host_keeps_the_views_order_in_node():
    node = shutil.which("node")
    assert node, "the sky's Node leg needs node on the PATH"
    run = subprocess.run([node, "--test", "--test-reporter=tap", str(ROOT / "tests" / "js" / "sky_host.test.mjs")], capture_output=True, text=True, timeout=120, cwd=ROOT)
    assert run.returncode == 0, run.stdout[-4000:] + run.stderr[-2000:]
    assert "# fail 0" in run.stdout and "# pass 0" not in run.stdout
