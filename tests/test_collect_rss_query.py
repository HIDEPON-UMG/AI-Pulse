"""RSS 検索クエリの不変条件契約テスト。

なぜ重要か（意図）:
  AI-Pulse の収集パイプライン (tools/collect_rss.py) は entity ごとの検索クエリで
  Google News RSS を叩く。クエリが AI 文脈を欠く ("Runway Runway" など一般英単語
  だけの組合せ) と、Rent the Runway (ファッションレンタル企業) / 空港の滑走路 /
  ファッションショーのランウェイのような AI ゼロの記事が大量に紛れ込み、サイトの
  「生成 AI 特化」というアイデンティティが直接崩れる。これは 2026-06-06 に runway
  カテゴリで実際に起きた事故 (10/11 件が AI 無関係)。

  本テストは「全 entity の build_query() 出力が AI 文脈ワードを少なくとも 1 つ含む」
  という不変条件を locked-in する ([[feedback_check_design_principles]] §4)。
  今後 entity を追加するときに、name+vendor 自動派生だけで AI 文脈が表現できない
  なら、entity に search_query フィールドを明示で書かないと CI が落ちる仕組み。

  - schema.py: search_query 任意フィールドの空文字禁止 (§1 illegal state)
  - collect_rss.build_query: search_query 優先 → name+vendor 派生の 1 経路 (§2 境界)
  - 本テスト: 全 entity に AI 文脈ワード必須 + runway 固有ガード (§4 契約)
  上 3 段で構造解決する。Lv5 個別 smoke は採用しない。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import collect_rss  # noqa: E402
import schema  # noqa: E402

DATA = ROOT / "data"

# AI 文脈ワード集合。1 つでも入っていれば「AI ニュースを引きに行くクエリ」と判定する。
# - 汎用語: 「これが入っていれば概ね AI ジャンルにヒットする」最小語彙
# - ベンダー / 製品固有名: AI-Pulse に登録済の全 vendor + 主要モデル名/プロダクト名
# 追加するときは「英文字列として一意に AI 文脈を引けるか」を基準に増やす。テストを甘く
# するために単語を増やすのは禁止 (Plan agile-beaming-kite.md リスク節)。
AI_CONTEXT_WORDS = frozenset({
    # 汎用ジャンル語
    "AI", "LLM", "model", "agent", "humanoid", "robot", "video",
    "image", "code", "coding", "generative",
    # ベンダー / 組織
    "OpenAI", "Anthropic", "Google", "Meta", "NVIDIA", "Microsoft",
    "Cursor", "Anysphere", "Alibaba", "DeepSeek", "Cognition",
    "Black Forest", "Physical Intelligence", "Figure", "Tesla",
    "Codeium", "LangChain", "LangGenius", "Nous Research",
    "CircleStone", "Civitai", "European Commission",
    # 製品 / モデル固有名
    "Claude", "Gemini", "FLUX", "GPT", "Cosmos", "Codex", "Llama",
    "Qwen", "Composer", "Windsurf", "Devin", "AgentKit", "Hermes Agent",
    "Ironwood", "Vera Rubin", "OpenClaw", "Anima", "WAI", "Dify",
    "LangGraph", "Optimus",
    # 政策・規制
    "EU AI Act", "Japan AI",
})


class TestRssQueryContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entities, _ = schema.validate_store(DATA / "entities.jsonl", DATA / "events.jsonl")

    def _query_has_ai_context(self, query: str) -> bool:
        """クエリ文字列に AI 文脈ワードが少なくとも 1 つ含まれるか。

        大文字小文字を無視する。複合語 ("Black Forest" など) は単一フレーズとして照合する。
        """
        q_lower = query.lower()
        return any(w.lower() in q_lower for w in AI_CONTEXT_WORDS)

    def test_all_entities_query_contains_ai_context(self):
        """全 entity に対して build_query() の出力が AI 文脈ワードを少なくとも 1 つ含む。

        これが落ちたら、その entity の name+vendor 自動派生では AI ニュースに絞れないので、
        entities.jsonl の該当行に search_query フィールドを明示で追加すること
        (例: runway -> "Runway AI video generation Gen-4 Aleph")。
        テストの語彙 (AI_CONTEXT_WORDS) を増やして逃げてはいけない。
        """
        offenders: list[tuple[str, str]] = []
        for ent in self.entities:
            q = collect_rss.build_query(ent)
            if not self._query_has_ai_context(q):
                offenders.append((ent["entity_id"], q))
        self.assertEqual(
            offenders,
            [],
            f"AI 文脈ワードを欠くクエリ: {offenders} — entity に search_query を追加してください",
        )

    def test_runway_query_requires_explicit_modifier(self):
        """runway は一般英単語 + 異義語企業 (Rent the Runway) が極端に多いため、

        単に "Runway" を含むだけでは不十分。"AI" / "video" / "Gen" のいずれかの修飾を
        必ず含むこと。runway entity の search_query フィールドを誤って削除/編集して
        修飾を落とすと、このテストが落ちる (Runway 固有のガード)。
        """
        runway = next((e for e in self.entities if e["entity_id"] == "runway"), None)
        self.assertIsNotNone(runway, "runway entity が存在しない (purge スクリプトの誤実行?)")
        q = collect_rss.build_query(runway)
        modifiers = ("AI", "video", "Gen")
        self.assertTrue(
            any(m.lower() in q.lower() for m in modifiers),
            f"runway クエリ {q!r} に AI/video/Gen のいずれの修飾も無い "
            f"— Rent the Runway や空港滑走路ニュースを引いてしまう",
        )

    def test_search_query_override_is_returned_verbatim(self):
        """search_query を明示した entity は build_query が strip 後のその値をそのまま返す。

        自動派生 (name+vendor) に fallback してはいけない。schema が空文字を弾いているので、
        ここでは「非空 search_query を持つ entity は build_query == search_query.strip()」のみ確認。
        """
        for ent in self.entities:
            sq = ent.get("search_query")
            if isinstance(sq, str) and sq.strip():
                self.assertEqual(
                    collect_rss.build_query(ent),
                    sq.strip(),
                    f"{ent['entity_id']}: search_query が build_query の戻り値と一致しない",
                )

    def test_empty_search_query_is_rejected_by_schema(self):
        """schema.validate_entity が空文字/空白だけの search_query を弾く。

        illegal state ("search_query があるが中身が空") を表現できなくする ([[feedback_check_design_principles]] §1)。
        """
        for bad in ("", "   ", "\t\n"):
            with self.assertRaises(schema.SchemaError):
                schema.validate_entity({
                    "entity_id": "test-bad-sq", "name": "Test", "kind": "app",
                    "domain": "test", "offering": "oss", "vendor": "Test",
                    "category": "agent", "snapshot_date": "2026-06-06",
                    "positioning": "テスト", "search_query": bad,
                })


if __name__ == "__main__":
    unittest.main()
