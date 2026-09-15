import pytest
from splitscreen.config import instance_from_dict
from splitscreen.session import run_pre_launch


def test_pre_launch_runs_in_order_and_logs(tmp_path):
    inst = instance_from_dict({"id": "a", "command": ["x"], "pre_launch": [["sh", "-c", "echo one"], ["sh", "-c", "echo two"]]})
    run_pre_launch(inst, tmp_path)
    log = (tmp_path / "a.log").read_text()
    assert log.index("one") < log.index("two")


def test_pre_launch_failure_aborts(tmp_path):
    inst = instance_from_dict({"id": "a", "command": ["x"], "pre_launch": [["sh", "-c", "exit 3"]]})
    with pytest.raises(RuntimeError, match="exit 3"):
        run_pre_launch(inst, tmp_path)
