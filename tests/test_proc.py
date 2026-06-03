"""契約テスト: subprocess 境界 quiet_run / spawn_detached が Windows で必ず CREATE_NO_WINDOW を付ける。

なぜ重要か（意図）:
  pythonw / Task Scheduler 配下で外部コマンド（notebooklm.exe / claude / git）を起動すると、
  CREATE_NO_WINDOW を付けない限り黒窓が点滅する。これは「付け忘れ」という 1 つの class of bug。
  個別呼び出し箇所すべてに注意するのではなく、境界 1 箇所（_proc.run）で必ず付くことだけを縛れば
  全呼び出しが守られる。本テストはその不変条件を 1 件で固定する。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from _proc import run as procrun  # noqa: E402

_EXPECTED = 0x08000000 if sys.platform == "win32" else 0


class _FakeCompleted:
    def __init__(self):
        self.stdout = ""
        self.stderr = ""
        self.returncode = 0


class TestQuietRunContract(unittest.TestCase):
    def _capture(self, target):
        """target('run' or 'Popen') の呼び出し kwargs を捕捉して返す。"""
        captured = {}

        def fake(args, **kw):
            captured["args"] = args
            captured.update(kw)
            return _FakeCompleted()

        orig = getattr(procrun.subprocess, target)
        setattr(procrun.subprocess, target, fake)
        try:
            if target == "run":
                procrun.quiet_run(["echo", "hi"], check=False)
            else:
                procrun.spawn_detached(["echo", "hi"])
        finally:
            setattr(procrun.subprocess, target, orig)
        return captured

    def test_quiet_run_sets_create_no_window(self):
        captured = self._capture("run")
        self.assertEqual(captured["creationflags"], _EXPECTED)

    def test_quiet_run_forces_capture_and_replace(self):
        captured = self._capture("run")
        self.assertTrue(captured["capture_output"])
        self.assertTrue(captured["text"])
        self.assertEqual(captured["errors"], "replace")

    def test_spawn_detached_sets_create_no_window(self):
        captured = self._capture("Popen")
        self.assertEqual(captured["creationflags"], _EXPECTED)

    def test_no_window_flags_matches_platform(self):
        self.assertEqual(procrun._no_window_flags(), _EXPECTED)


if __name__ == "__main__":
    unittest.main()
