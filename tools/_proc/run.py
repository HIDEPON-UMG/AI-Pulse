"""subprocess 境界モジュール（唯一の起動点）。

Windows の pythonw / --noconsole / Task Scheduler 配下では、子コンソールアプリ
（notebooklm.exe / claude / git 等）を起動すると黒窓が一瞬点滅する。これを防ぐため
Windows では CREATE_NO_WINDOW を必ず OR する。AI-Pulse の全 subprocess 起動は
本モジュールの quiet_run / spawn_detached だけを通す（pyproject の banned-api lint で
subprocess 直呼びを全 ban し、本ファイルだけ per-file-ignore で許可）。

契約テスト tests/test_proc.py が「Windows なら必ず CREATE_NO_WINDOW を付ける」を 1 件で固定する。
"""
from __future__ import annotations

import subprocess
import sys

_CREATE_NO_WINDOW = 0x08000000  # Windows: 子に新規 console を割り当てない


def _no_window_flags() -> int:
    """Windows のみ CREATE_NO_WINDOW。他 OS は 0（無害）。"""
    return _CREATE_NO_WINDOW if sys.platform == "win32" else 0


def quiet_run(args, *, timeout=None, cwd=None, check=True, input=None):
    """同期実行。stdout/stderr を捕捉して CompletedProcess を返す。Windows は黒窓を出さない。

    cp932 化け対策に text=True / encoding="utf-8" / errors="replace" を強制する。
    """
    return subprocess.run(  # noqa: TID251  (境界モジュールのみ subprocess 直呼び許可)
        [str(a) for a in args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=cwd,
        check=check,
        input=input,
        creationflags=_no_window_flags(),
    )


def spawn_detached(args, *, cwd=None, stdout=None):
    """非同期キック（待たない）。深掘りジョブ 段A の deep research 起動に使う。Popen を返す。"""
    return subprocess.Popen(  # noqa: TID251
        [str(a) for a in args],
        cwd=cwd,
        stdout=stdout if stdout is not None else subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        creationflags=_no_window_flags(),
    )
