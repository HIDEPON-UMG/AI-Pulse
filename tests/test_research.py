"""リサーチ系の決定論パートのテスト（外部エンジンは fake で差し替え）。

実機の WebSearch / NotebookLM / ネットワークは呼ばない。本テストが固定するのは
「Python スパインが正しく引数を組み・回答を解釈し・カルテへ反映するか」という決定論部分。
実エンジン込みの E2E は live cookie / claude -p が要るため Step 7（自動化）で別途行う。
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import research_websearch as rws  # noqa: E402
import research_notebooklm as rnb  # noqa: E402
import verify_quant  # noqa: E402
import schema  # noqa: E402


class _CP:
    """CompletedProcess の最小スタブ。"""
    def __init__(self, stdout=""):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


def _entity(eid="claude-opus"):
    return {
        "entity_id": eid, "name": "E", "kind": "model", "domain": "language",
        "offering": "commercial", "vendor": "V", "category": "model",
        "snapshot_date": "2026-05-01", "positioning": "p",
    }


def _event(evid="e1", eid="claude-opus", score=80):
    return {
        "event_id": evid, "entity_id": eid, "date": "2026-06-02", "category": "model",
        "event_type": "release", "headline": "h", "summary": "s",
        "score": score, "importance": "high", "source": "src", "source_tier": "T1",
    }


class TestWebsearchIngest(unittest.TestCase):
    def setUp(self):
        self.tmp = ROOT / "tests" / "_tmp_rws"
        self.tmp.mkdir(exist_ok=True)
        self.ents = self.tmp / "entities.jsonl"
        self.evs = self.tmp / "events.jsonl"
        self.ents.write_text(json.dumps(_entity(), ensure_ascii=False) + "\n", encoding="utf-8")
        self.evs.write_text("", encoding="utf-8")

    def tearDown(self):
        for p in (self.ents, self.evs):
            if p.exists():
                p.unlink()
        if self.tmp.exists() and not any(self.tmp.iterdir()):
            self.tmp.rmdir()

    def test_ingest_breaking_persists_via_store(self):
        r = rws.ingest_breaking([_event()], entities_path=self.ents, events_path=self.evs)
        self.assertEqual(len(r["added"]), 1)
        _, events = schema.validate_store(self.ents, self.evs)
        self.assertEqual(events[0]["event_id"], "e1")


class TestNotebookLMDriver(unittest.TestCase):
    def setUp(self):
        self.jobs = ROOT / "tests" / "_tmp_jobs"
        self.jobs.mkdir(exist_ok=True)
        self._orig_jobs = rnb.JOBS
        rnb.JOBS = self.jobs

    def tearDown(self):
        rnb.JOBS = self._orig_jobs
        for p in self.jobs.glob("*.json"):
            p.unlink()
        if self.jobs.exists() and not any(self.jobs.iterdir()):
            self.jobs.rmdir()

    def test_kick_deep_parses_id_and_saves_job(self):
        spawned = {}

        def fake_runner(args, timeout=120):
            return _CP(stdout="created notebook nbk-abc12345\n") if "create" in args else _CP()

        def fake_spawner(args):
            spawned["args"] = args

        nid = rnb.kick_deep("claude-opus", "Claude Opus 最新", runner=fake_runner, spawner=fake_spawner)
        self.assertEqual(nid, "nbk-abc12345")
        # デタッチ起動の引数に deep / import-all が含まれる
        self.assertIn("add-research", spawned["args"])
        self.assertIn("--mode", spawned["args"])
        self.assertIn("deep", spawned["args"])
        # job-state が保存されている
        job = json.loads((self.jobs / "claude-opus.json").read_text(encoding="utf-8"))
        self.assertEqual(job["notebook_id"], "nbk-abc12345")
        self.assertEqual(job["status"], "researching")

    def test_ensure_auth_logs_in_when_refresh_is_expired(self):
        calls = []

        def fake_runner(args, timeout=120):
            calls.append(args[1:])
            if args[1:] == ["auth", "refresh"] and len(calls) == 1:
                raise RuntimeError("Authentication expired")
            return _CP(stdout="ok")

        rnb.ensure_auth(runner=fake_runner)
        self.assertEqual(calls, [["auth", "refresh"], ["login"], ["auth", "refresh"]])

    def test_ensure_auth_can_skip_login_for_noninteractive_runs(self):
        calls = []

        def fake_runner(args, timeout=120):
            calls.append(args[1:])
            raise RuntimeError("Authentication expired")

        with self.assertRaisesRegex(RuntimeError, "非対話実行"):
            rnb.ensure_auth(runner=fake_runner, allow_login=False)
        self.assertEqual(calls, [["auth", "refresh"]])

    def test_ensure_auth_does_not_login_when_refresh_succeeds(self):
        calls = []

        def fake_runner(args, timeout=120):
            calls.append(args[1:])
            return _CP(stdout="ok")

        rnb.ensure_auth(runner=fake_runner)
        self.assertEqual(calls, [["auth", "refresh"]])

    def test_kick_deep_explicit_id_skips_parsing(self):
        """notebook_id を明示指定すれば create 出力のパースに依存しない安全経路。"""
        calls = {"args": []}

        def fake_runner(args, timeout=120):
            calls["args"].append(args)
            return _CP()

        nid = rnb.kick_deep("claude-opus", "テーマ", notebook_id="nbk-explicit99",
                            runner=fake_runner, spawner=lambda a: None)
        self.assertEqual(nid, "nbk-explicit99")
        # create は呼ばれない（use のみ）
        self.assertFalse(any("create" in a for a in calls["args"]))

    def test_collect_returns_researching_when_not_ready(self):
        (self.jobs / "claude-opus.json").write_text(
            json.dumps({"entity_id": "claude-opus", "notebook_id": "nbk-1", "status": "researching"}),
            encoding="utf-8")

        def fake_runner(args, timeout=120):
            if "list" in args:
                return _CP(stdout=json.dumps([{"status": "importing"}]))
            return _CP(stdout="{}")

        out = rnb.collect("claude-opus", ["Q1"], runner=fake_runner)
        self.assertFalse(out["ready"])
        self.assertEqual(out["status"], "researching")

    def test_collect_asks_when_ready(self):
        (self.jobs / "claude-opus.json").write_text(
            json.dumps({"entity_id": "claude-opus", "notebook_id": "nbk-1", "status": "researching"}),
            encoding="utf-8")

        def fake_runner(args, timeout=120):
            if "list" in args:
                return _CP(stdout=json.dumps([{"status": "ready"}, {"status": "ready"}]))
            if "ask" in args:
                return _CP(stdout=json.dumps({"answer": "...", "citations": [1, 2]}))
            return _CP(stdout="{}")

        out = rnb.collect("claude-opus", ["俯瞰", "競合"], runner=fake_runner)
        self.assertTrue(out["ready"])
        self.assertEqual(len(out["answers"]), 2)


class TestApplyDeepdive(unittest.TestCase):
    def setUp(self):
        self.tmp = ROOT / "tests" / "_tmp_dd"
        self.tmp.mkdir(exist_ok=True)
        self.ents = self.tmp / "entities.jsonl"
        self.evs = self.tmp / "events.jsonl"
        self.ents.write_text(json.dumps(_entity(), ensure_ascii=False) + "\n", encoding="utf-8")
        self.evs.write_text("", encoding="utf-8")

    def tearDown(self):
        for p in (self.ents, self.evs):
            if p.exists():
                p.unlink()
        if self.tmp.exists() and not any(self.tmp.iterdir()):
            self.tmp.rmdir()

    def test_apply_deepdive_merges_and_revalidates(self):
        ent = rnb.apply_deepdive(
            "claude-opus", {"positioning": "更新後の位置づけ", "competitors": ["GPT"]},
            entities_path=self.ents, events_path=self.evs)
        self.assertEqual(ent["positioning"], "更新後の位置づけ")
        entities, _ = schema.validate_store(self.ents, self.evs)
        self.assertEqual(entities[0]["positioning"], "更新後の位置づけ")

    def test_apply_deepdive_rejects_schema_breaking_update(self):
        """反映後に schema を壊す更新（未知 category）は弾く。"""
        with self.assertRaises(schema.SchemaError):
            rnb.apply_deepdive("claude-opus", {"category": "UNKNOWN"},
                               entities_path=self.ents, events_path=self.evs)

    def test_apply_deepdive_unknown_entity_raises(self):
        with self.assertRaises(schema.SchemaError):
            rnb.apply_deepdive("ghost", {"positioning": "x"},
                               entities_path=self.ents, events_path=self.evs)


class TestVerifyQuant(unittest.TestCase):
    def test_verified_when_number_present(self):
        out = verify_quant.verify("128000", "http://x", fetcher=lambda u: "context 128000 tokens")
        self.assertTrue(out["verified"])

    def test_comma_and_fullwidth_normalized(self):
        out = verify_quant.verify("1000000", "http://x", fetcher=lambda u: "最大 1,000,000 トークン")
        self.assertTrue(out["verified"])
        out2 = verify_quant.verify("128000", "http://x", fetcher=lambda u: "全角 １２８０００ です")
        self.assertTrue(out2["verified"])

    def test_unverified_when_absent(self):
        out = verify_quant.verify("999999", "http://x", fetcher=lambda u: "no such number here")
        self.assertFalse(out["verified"])


if __name__ == "__main__":
    unittest.main()
