"""契約テスト: 書き込み境界 store の不変条件。

なぜ重要か（意図）:
  サイトの導線は「新着デルタ → カルテ深掘り」。これを支えるのが
  (1) デルタ→カルテのフックがリンク切れを作らないこと、
  (2) snapshot_date を古いニュースで巻き戻さないこと、
  (3) 同一ニュースを二重登録しない（同日重複）こと。
  ビジネスロジック（スコア式・レンズ増減）が変わっても、この 3 つが崩れたら必ず落ちる。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import store  # noqa: E402
import schema  # noqa: E402
import config  # noqa: E402


def _entity(eid="claude-opus", snapshot="2026-05-01"):
    return {
        "entity_id": eid, "name": "E", "kind": "model", "domain": "language",
        "offering": "commercial", "vendor": "V", "category": "model",
        "snapshot_date": snapshot, "positioning": "p",
    }


def _event(evid="e1", eid="claude-opus", date="2026-06-02", score=80, headline="h"):
    return {
        "event_id": evid, "entity_id": eid, "date": date, "category": "model",
        "event_type": "release", "headline": headline, "summary": "s",
        "score": score, "importance": "high", "source": "src", "source_tier": "T1",
    }


class TestCarteHook(unittest.TestCase):
    def test_dangling_reference_raises(self):
        """参照先カルテが無いフックは弾く（リンク切れを表現させない）。"""
        with self.assertRaises(schema.SchemaError):
            store.apply_carte_hook(_event(eid="ghost"), {"claude-opus": _entity()})

    def test_snapshot_moves_forward_only(self):
        """新しいニュースは snapshot を進め、古いニュースは巻き戻さない。"""
        ent = _entity(snapshot="2026-05-01")
        store.apply_carte_hook(_event(date="2026-06-02"), {"claude-opus": ent})
        self.assertEqual(ent["snapshot_date"], "2026-06-02")
        store.apply_carte_hook(_event(evid="e2", date="2026-04-01"), {"claude-opus": ent})
        self.assertEqual(ent["snapshot_date"], "2026-06-02", "古いニュースで巻き戻った")

    def test_backlink_is_deduped_and_capped(self):
        """recent_events は重複せず上限 cap で打ち切る。"""
        ent = _entity()
        for i in range(config.RECENT_EVENTS_CAP + 5):
            store.apply_carte_hook(_event(evid=f"e{i}", headline=f"h{i}"), {"claude-opus": ent})
        self.assertEqual(len(ent["recent_events"]), config.RECENT_EVENTS_CAP)
        # 同じ event_id を二度入れても増えない
        before = list(ent["recent_events"])
        store.apply_carte_hook(_event(evid=before[0], headline="dup"), {"claude-opus": ent})
        self.assertEqual(ent["recent_events"], before)


class TestDedupAndScore(unittest.TestCase):
    def test_same_id_or_content_is_dropped(self):
        existing = [_event(evid="e1")]
        new = [_event(evid="e1"), _event(evid="e2-DIFF")]  # e1=id重複, 2件目=内容同一
        kept, dup = store.dedupe_events(new, existing)
        self.assertEqual(len(kept), 0)
        self.assertEqual(len(dup), 2)

    def test_score_threshold(self):
        keep, drop = store.filter_by_score([_event(score=80), _event(score=10)], score_min=50)
        self.assertEqual(len(keep), 1)
        self.assertEqual(len(drop), 1)


class TestIngestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = ROOT / "tests" / "_tmp"
        self.tmp.mkdir(exist_ok=True)
        self.ents = self.tmp / "entities.jsonl"
        self.evs = self.tmp / "events.jsonl"
        import json
        self.ents.write_text(json.dumps(_entity(snapshot="2026-05-01"), ensure_ascii=False) + "\n",
                             encoding="utf-8")
        self.evs.write_text("", encoding="utf-8")

    def tearDown(self):
        for p in (self.ents, self.evs):
            if p.exists():
                p.unlink()
        if self.tmp.exists() and not any(self.tmp.iterdir()):
            self.tmp.rmdir()

    def test_ingest_persists_and_updates_carte(self):
        """採用 1 / 閾値スキップ 1。永続化後、カルテ snapshot が前進し event が解決する。"""
        candidates = [_event(evid="hi", score=80, date="2026-06-02"),
                      _event(evid="lo", score=10, headline="low", date="2026-06-02")]
        r = store.ingest_events(self.ents, self.evs, candidates)
        self.assertEqual(len(r["added"]), 1)
        self.assertEqual(r["skipped_score"], 1)
        # 永続結果を再ロードして参照整合と snapshot 前進を確認
        entities, events = schema.validate_store(self.ents, self.evs)
        self.assertEqual(len(events), 1)
        ent = {e["entity_id"]: e for e in entities}["claude-opus"]
        self.assertEqual(ent["snapshot_date"], "2026-06-02")
        self.assertIn("hi", ent["recent_events"])

    def test_unknown_entity_candidate_raises(self):
        """既知カルテに紐づかない候補は検証で弾く（速報は新規カルテを作らない）。"""
        with self.assertRaises(schema.SchemaError):
            store.ingest_events(self.ents, self.evs, [_event(evid="x", eid="ghost")])


if __name__ == "__main__":
    unittest.main()
