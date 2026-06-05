"""AI-Pulse スキーマ契約テスト。

なぜ重要か（意図）:
  サイトの核は「新着フィード（L2 デルタ）から対象サービスの分析カルテ（L1）へ深掘り」
  という導線。これは L2.entity_id → L1.entity_id の参照で成り立つ。
  参照が壊れる / 未知の分類値が混じると、フィードのリンク切れ・カテゴリ色の欠落として
  ユーザーに直接露出する。よってこのテストは「参照整合」と「分類の閉じ」を不変条件として固定する。
  ビジネスロジック（スコア式やレンズの増減）が変わっても、この 2 つが崩れたら必ず落ちる。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import schema  # noqa: E402

DATA = ROOT / "data"


class TestSchemaContract(unittest.TestCase):
    def test_store_loads_and_all_refs_resolve(self):
        """本番 jsonl が全行スキーマを通過し、全 event の entity_id が解決する。"""
        entities, events = schema.validate_store(DATA / "entities.jsonl", DATA / "events.jsonl")
        self.assertGreater(len(entities), 0, "entities が空")
        self.assertGreater(len(events), 0, "events が空")
        ids = {e["entity_id"] for e in entities}
        for ev in events:
            self.assertIn(ev["entity_id"], ids, f"{ev['event_id']} の参照が宙ぶらり")

    def test_dangling_event_reference_is_rejected(self):
        """存在しない entity を指す event は弾く（リンク切れを表現できない）。"""
        with self.assertRaises(schema.SchemaError):
            schema.validate_event(
                {"event_id": "x", "entity_id": "does-not-exist", "date": "2026-06-02",
                 "category": "model", "event_type": "release", "headline": "h", "summary": "s",
                 "score": 50, "importance": "high", "source": "x", "source_tier": "T1"},
                known_entity_ids={"claude-opus"})

    def test_unknown_category_is_rejected(self):
        """7 レンズ外の category は弾く（色・グリフ未割当を防ぐ）。"""
        with self.assertRaises(schema.SchemaError):
            schema.validate_entity(
                {"entity_id": "e", "name": "E", "kind": "app", "domain": "x", "offering": "oss",
                 "vendor": "v", "category": "UNKNOWN", "snapshot_date": "2026-06-02", "positioning": "p"})

    def test_score_out_of_range_is_rejected(self):
        """ニュース性スコアは 0-100 に閉じる。"""
        with self.assertRaises(schema.SchemaError):
            schema.validate_event(
                {"event_id": "x", "entity_id": "claude-opus", "date": "2026-06-02",
                 "category": "model", "event_type": "release", "headline": "h", "summary": "s",
                 "score": 150, "importance": "high", "source": "x", "source_tier": "T1"},
                known_entity_ids={"claude-opus"})

    def test_history_is_well_formed_when_present(self):
        """テクニカル・ヒストリーがあるなら各項目に when/title を要求する。

        なぜ重要か: カルテのタイムラインは history を {when,title,note,now} で描く。
        when/title を欠いた項目を通すと「日付も見出しも無い空マイルストーン」を
        ユーザーに見せてしまう（捏造に近い空表示）。任意項目だが、入れるなら形を固定する。
        """
        base = {"entity_id": "e", "name": "E", "kind": "app", "domain": "x", "offering": "oss",
                "vendor": "v", "category": "model", "snapshot_date": "2026-06-02", "positioning": "p"}
        # when 欠落は弾く
        with self.assertRaises(schema.SchemaError):
            schema.validate_entity({**base, "history": [{"title": "公開"}]})
        # now が bool でないのは弾く
        with self.assertRaises(schema.SchemaError):
            schema.validate_entity({**base, "history": [{"when": "2024.03", "title": "公開", "now": "yes"}]})
        # url が http でないのは弾く
        with self.assertRaises(schema.SchemaError):
            schema.validate_entity({**base, "history": [{"when": "2024.03", "title": "公開", "url": "javascript:1"}]})
        # 整形済みは通る（history 無し・空配列も任意項目として通る）
        ok = schema.validate_entity({**base, "history": [{"when": "2024.03", "title": "公開", "now": True}]})
        self.assertEqual(len(ok["history"]), 1)
        self.assertEqual(schema.validate_entity(base), base)

    def test_history_must_be_newest_first(self):
        """最新(now=true)は先頭でないと弾く。

        なぜ重要か: タイムラインは横で左/縦で上から DOM 順に並ぶ。技術トレンドは「最新が何か」が
        最重要なので、最新を先頭に固定する。古い順で書かれると最新が右端/最下部に隠れる回帰を防ぐ。
        """
        base = {"entity_id": "e", "name": "E", "kind": "app", "domain": "x", "offering": "oss",
                "vendor": "v", "category": "model", "snapshot_date": "2026-06-02", "positioning": "p"}
        with self.assertRaises(schema.SchemaError):
            schema.validate_entity({**base, "history": [
                {"when": "2024.03", "title": "旧"}, {"when": "2026.05", "title": "新", "now": True}]})
        ok = schema.validate_entity({**base, "history": [
            {"when": "2026.05", "title": "新", "now": True}, {"when": "2024.03", "title": "旧"}]})
        self.assertTrue(ok["history"][0]["now"])

    def test_comparison_axes_are_lens_shared_and_complete(self):
        """比較軸はレンズ(category)共通が単一ソース（方針B）。entity 独自軸は不可、

        かつ全 col が所属レンズの全軸セルを持つ（穴あき表を防ぐ）。"""
        base = {"entity_id": "e", "name": "E", "kind": "app", "domain": "x", "offering": "oss",
                "vendor": "v", "category": "model", "snapshot_date": "2026-06-02", "positioning": "p"}
        model_keys = [a["key"] for a in schema.LENS_AXES["model"]]
        full_cells = {k: {"v": "x"} for k in model_keys}
        # レンズ全キーを埋めた cols だけの comparison は通り、軸はレンズから注入される（entity は axes を持たない）
        ok = schema.validate_entity({**base, "comparison": {"cols": [{"name": "E", "self": True, "cells": full_cells}]}})
        self.assertIsNotNone(ok["comparison"])
        # entity が独自 axes を持つのは弾く（軸はレンズ共通）
        with self.assertRaises(schema.SchemaError):
            schema.validate_entity({**base, "comparison": {"axes": [{"key": "a", "label": "A"}],
                                    "cols": [{"name": "E", "cells": full_cells}]}})
        # レンズ軸のセル欠落は弾く
        holey = {k: {"v": "x"} for k in model_keys[:-1]}  # 末尾キー欠落
        with self.assertRaises(schema.SchemaError):
            schema.validate_entity({**base, "comparison": {"cols": [{"name": "E", "cells": holey}]}})

    def test_future_items_require_label_and_title(self):
        """将来シナリオ各項目は label/title 必須（空シナリオ枠の描画を防ぐ）。"""
        base = {"entity_id": "e", "name": "E", "kind": "app", "domain": "x", "offering": "oss",
                "vendor": "v", "category": "model", "snapshot_date": "2026-06-02", "positioning": "p"}
        with self.assertRaises(schema.SchemaError):
            schema.validate_entity({**base, "modules": {"future": [{"title": "t"}]}})
        # url があるなら http(s) を要求（出典リンクの健全性。定量予測の出典に偽 URL を載せない）
        with self.assertRaises(schema.SchemaError):
            schema.validate_entity({**base, "modules": {"future": [
                {"label": "近", "title": "t", "url": "ftp://x"}]}})
        ok = schema.validate_entity({**base, "modules": {"future": [{"label": "近", "title": "t", "note": "n"}]}})
        self.assertEqual(len(ok["modules"]["future"]), 1)

    def test_event_extras_are_well_formed_when_present(self):
        """L2 デルタの拡張（出典URL・カルテ更新フラグ・要点・判断根拠）は、入れるなら形を固定する。

        なぜ重要か: フィードは本体クリックで source_url（出典記事）へ飛び、karte_updated で
        UPDATE バッジを出し、summary_points を箇条書き・rationale を3指標の判断根拠として描く。
        偽 URL・非 bool・件数過多/過少・根拠欠落を通すと、リンク切れや空表示・誇張表示として
        ユーザーに直接露出する。任意項目だが、入れるなら形を固定して回帰を防ぐ。
        """
        base = {"event_id": "x", "entity_id": "claude-opus", "date": "2026-06-02",
                "category": "model", "event_type": "release", "headline": "h", "summary": "s",
                "score": 80, "importance": "high", "source": "x", "source_tier": "T1"}
        ids = {"claude-opus"}
        # source_url が http でないのは弾く（出典リンクの健全性）
        with self.assertRaises(schema.SchemaError):
            schema.validate_event({**base, "source_url": "javascript:alert(1)"}, ids)
        # karte_updated が bool でないのは弾く
        with self.assertRaises(schema.SchemaError):
            schema.validate_event({**base, "karte_updated": "yes"}, ids)
        # summary_points は 3〜5 件（6 件は弾く / 2 件も弾く）
        with self.assertRaises(schema.SchemaError):
            schema.validate_event({**base, "summary_points": [f"p{i}" for i in range(6)]}, ids)
        with self.assertRaises(schema.SchemaError):
            schema.validate_event({**base, "summary_points": ["p1", "p2"]}, ids)
        # rationale は重要/影響/話題の3キーを揃える（穴あき根拠を防ぐ）
        with self.assertRaises(schema.SchemaError):
            schema.validate_event({**base, "rationale": {"importance": "x", "impact": "y"}}, ids)
        # rationale の各値が短すぎる（"high"/"mid" 等のラベル反復）は弾く
        # ([[feedback_check_design_principles]] §1 + §4 / 2026-06-05 Part 7)
        with self.assertRaises(schema.SchemaError):
            schema.validate_event({**base, "rationale": {"importance": "high", "impact": "high", "buzz": "high"}}, ids)
        with self.assertRaises(schema.SchemaError):
            schema.validate_event({**base, "rationale": {"importance": "高と判定", "impact": "高と判定", "buzz": "高と判定"}}, ids)
        # 整形済みは通る (各値 20 字以上の文章)
        ok = schema.validate_event(
            {**base, "source_url": "https://example.com/a", "karte_updated": True,
             "summary_points": ["p1", "p2", "p3"],
             "rationale": {
                "importance": "最上位モデルのメジャー更新で基盤に関わるため重要度を高と判定。",
                "impact": "下流のコーディングツールが採用モデルを更新する波及があるため影響度を高と判定。",
                "buzz": "Anthropic 公式発表でニュース性スコア85。コミュニティ注目が大きく話題性を高と判定。"}}, ids)
        self.assertEqual(len(ok["summary_points"]), 3)
        self.assertTrue(ok["karte_updated"])

    def test_related_entities_form_and_refs(self):
        """related_entities は任意の補助配列だが、入れるなら形と参照整合を固定する（案 B / 2026-06-04）。

        なぜ重要か: 1 件のニュースが複数 entity に紐づくケースを表現する補助フィールド。
        非リスト・空文字・主entity重複・上限超過・未知 entity_id を通すと、フィード/アーカイブ
        の karte_chips に偽カルテ名や重複が出る。任意項目だが、入れるなら形を固定して回帰を防ぐ。
        """
        base = {"event_id": "x", "entity_id": "claude-opus", "date": "2026-06-02",
                "category": "model", "event_type": "release", "headline": "h", "summary": "s",
                "score": 80, "importance": "high", "source": "x", "source_tier": "T1"}
        ids = {"claude-opus", "cursor", "gemini"}
        # 主 entity_id を related に含めるのは弾く（重複表示の防止）
        with self.assertRaises(schema.SchemaError):
            schema.validate_event({**base, "related_entities": ["claude-opus"]}, ids)
        # 配列以外は弾く
        with self.assertRaises(schema.SchemaError):
            schema.validate_event({**base, "related_entities": "cursor"}, ids)
        # 空文字を含む配列は弾く
        with self.assertRaises(schema.SchemaError):
            schema.validate_event({**base, "related_entities": ["cursor", ""]}, ids)
        # 5 件超は弾く
        with self.assertRaises(schema.SchemaError):
            schema.validate_event(
                {**base, "related_entities": [f"x{i}" for i in range(6)]}, ids)
        # 重複は弾く
        with self.assertRaises(schema.SchemaError):
            schema.validate_event({**base, "related_entities": ["cursor", "cursor"]}, ids)
        # 未知 entity_id を参照するのは弾く（L1 に存在しない）
        with self.assertRaises(schema.SchemaError):
            schema.validate_event({**base, "related_entities": ["ghost"]}, ids)
        # 正常なケースは通る
        ok = schema.validate_event({**base, "related_entities": ["cursor", "gemini"]}, ids)
        self.assertEqual(ok["related_entities"], ["cursor", "gemini"])
        # 未指定 / 空配列は許容（任意項目）
        self.assertIsNone(schema.validate_event(base, ids).get("related_entities"))
        self.assertEqual(
            schema.validate_event({**base, "related_entities": []}, ids).get("related_entities"),
            [])

    def test_source_url_blocks_xss_payloads(self):
        """source_url に JS リテラル / HTML 属性を破壊する文字を含めると ingest 時に弾く。

        なぜ重要か: index.html.j2 が onclick 内で source_url を JS 文字列リテラルに埋める設計で、
        Jinja autoescape は HTML エンティティしかエスケープせず JS の single quote `'` は素通り。
        ingest 時点で illegal state を表現できないようにすることで、SSG 後の DOM XSS を封じる。
        publisher 側が悪意ある URL（gnewsdecoder の resolve 経由で `'`+JS payload）を返した場合の
        防衛線。class of bugs を 1 ルールで構造的に塞ぐ（feedback_check_design_principles §1）。
        """
        base = {"event_id": "x", "entity_id": "claude-opus", "date": "2026-06-02",
                "category": "model", "event_type": "release", "headline": "h", "summary": "s",
                "score": 80, "importance": "high", "source": "x", "source_tier": "T1"}
        ids = {"claude-opus"}
        # JS 文字列を脱出しうる single quote を含む URL は拒否
        with self.assertRaises(schema.SchemaError):
            schema.validate_event({**base, "source_url": "https://x.example.com/a'-alert(1)-'b"}, ids)
        # double quote も同様（HTML 属性脱出）
        with self.assertRaises(schema.SchemaError):
            schema.validate_event({**base, "source_url": 'https://x.example.com/a"onmouseover=alert(1)'}, ids)
        # 改行・タブ・NUL も拒否
        with self.assertRaises(schema.SchemaError):
            schema.validate_event({**base, "source_url": "https://x.example.com/\nalert(1)"}, ids)
        # scheme が http(s) でないものを拒否
        with self.assertRaises(schema.SchemaError):
            schema.validate_event({**base, "source_url": "file:///etc/passwd"}, ids)
        with self.assertRaises(schema.SchemaError):
            schema.validate_event({**base, "source_url": "data:text/html,<script>alert(1)</script>"}, ids)
        # hostname 欠落は拒否
        with self.assertRaises(schema.SchemaError):
            schema.validate_event({**base, "source_url": "https:///path"}, ids)
        # 正常な URL は通る
        ok = schema.validate_event({**base, "source_url": "https://example.com/article/123?q=foo&p=1"}, ids)
        self.assertTrue(ok["source_url"].startswith("https://"))


class TestEntityComparisonCoverage(unittest.TestCase):
    """ユーザー指摘 (2026-06-04): comparison は「比較対象が存在しない (= 同 category 内に
    entity が 1 件しか無い) ときだけ optional」であり、2 件以上あるなら必須である。
    schema 上は型として optional のままだが (regulation など category 単独 entity 用)、
    本番データの「比較対象がある以上は表で見せる」設計意図を契約テスト 1 件で locked-in する
    (feedback_check_design_principles の 4 段目)。

    弱い旧版「1 件でも comparison があれば全件必須」は『category 初の 1 件目を持たずに通す』
    抜け穴があり、ユーザー意図 (= 比較対象がある時点で必須) より緩かったため強化。
    """

    def test_comparison_is_required_when_category_has_peers(self):
        """本番 entities.jsonl で、同 category に entity が 2 つ以上ある (= 比較対象が
        存在する) 場合、その category の全 entity は comparison を持つ。"""
        entities, _ = schema.validate_store(DATA / "entities.jsonl", DATA / "events.jsonl")
        by_cat: dict[str, list[dict]] = {}
        for e in entities:
            by_cat.setdefault(e["category"], []).append(e)
        violations: list[str] = []
        for cat, items in by_cat.items():
            if len(items) < 2:  # 単独 entity の category は optional 許容
                continue
            missing = [e for e in items if not e.get("comparison")]
            if missing:
                violations.append(
                    f"category={cat!r} ({len(items)} 件): comparison 欠落 "
                    f"{[e['entity_id'] for e in missing]} (比較対象がいるので必須)"
                )
        self.assertFalse(
            violations,
            "比較対象がいる category で comparison 欠落:\n  - "
            + "\n  - ".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
