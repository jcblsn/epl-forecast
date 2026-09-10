import plistlib
from pathlib import Path

from epl_forecast import prospective


def test_launch_agent_replaces_any_earlier_job(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(
        prospective.subprocess, "run", lambda command, **kwargs: calls.append(command)
    )
    root = tmp_path / "runs"
    path = prospective.install_launch_agent(
        "org.epl-forecast.test", ["/bin/echo", "hello"], root, 3600, logs="operate"
    )
    config = plistlib.loads(path.read_bytes())
    assert config["Label"] == "org.epl-forecast.test"
    assert config["ProgramArguments"] == ["/bin/echo", "hello"]
    assert config["StartInterval"] == 3600
    assert config["StandardOutPath"] == str(root.resolve() / "operate.log")
    assert config["StandardErrorPath"] == str(root.resolve() / "operate-errors.log")
    assert [command[1] for command in calls] == ["bootout", "bootstrap"]
