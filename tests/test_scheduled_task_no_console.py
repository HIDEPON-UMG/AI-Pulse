from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_scheduled_tasks_use_pythonw_launcher() -> None:
    installer = (ROOT / "scripts" / "install_scheduled_tasks.ps1").read_text(encoding="utf-8-sig")
    launcher = (ROOT / "scripts" / "ai_pulse_task_launcher.pyw").read_text(encoding="utf-8")
    assert "pythonw.exe" in installer
    assert "ai_pulse_task_launcher.pyw" in installer
    assert "powershell.exe" not in installer
    assert "CREATE_NO_WINDOW" in launcher
    assert "--probe" in launcher
