"""subprocess 境界パッケージ。外部コマンド起動は run.quiet_run / run.spawn_detached のみ。"""
from .run import quiet_run, spawn_detached  # noqa: F401
