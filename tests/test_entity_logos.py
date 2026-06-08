import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import backfill_entity_logos as logos  # noqa: E402
import generate_pages as gp  # noqa: E402
import schema  # noqa: E402


class TestEntityLogoSchema(unittest.TestCase):
    def base_entity(self) -> dict:
        return {
            "entity_id": "sample",
            "name": "Sample",
            "kind": "app",
            "domain": "code",
            "offering": "commercial",
            "vendor": "Sample Inc.",
            "category": "editor",
            "snapshot_date": "2026-06-08",
            "positioning": "p",
        }

    def test_logo_field_accepts_local_png_path_for_ppt_and_ssg(self):
        entity = self.base_entity()
        entity["logo"] = {
            "path": "assets/service-icons/sample.png",
            "source_url": "https://example.com/logo.png",
            "source_page": "https://example.com/brand",
            "fetched_at": "2026-06-08",
            "license_note": "official site asset, redistribution not verified",
            "status": "verified",
        }
        self.assertEqual(schema.validate_entity(entity)["logo"]["status"], "verified")

    def test_logo_field_rejects_unsafe_path_and_bad_status(self):
        entity = self.base_entity()
        entity["logo"] = {"path": "../sample.png", "status": "verified"}
        with self.assertRaises(schema.SchemaError):
            schema.validate_entity(entity)
        entity["logo"] = {"status": "unknown"}
        with self.assertRaises(schema.SchemaError):
            schema.validate_entity(entity)


class TestEntityLogoGenerate(unittest.TestCase):
    def test_karte_pages_render_logo_when_entity_has_logo(self):
        ent = {
            "entity_id": "x",
            "name": "X",
            "kind": "model",
            "domain": "language",
            "offering": "oss",
            "vendor": "V",
            "category": "model",
            "snapshot_date": "2026-06-08",
            "positioning": "p",
            "logo": {
                "path": "assets/service-icons/x.png",
                "source_url": "https://example.com/x.png",
                "source_page": "https://example.com/brand",
                "fetched_at": "2026-06-08",
                "license_note": "official site asset, redistribution not verified",
                "status": "candidate",
            },
        }
        ev = {
            "event_id": "e1",
            "entity_id": "x",
            "date": "2026-06-08",
            "category": "model",
            "event_type": "release",
            "headline": "h",
            "summary": "s",
            "score": 90,
            "importance": "high",
            "source": "src",
            "source_tier": "T1",
        }
        ctx = gp.build_context([ent], [ev])
        html = gp.make_env().get_template("karte.html.j2").render(
            **ctx, page="karte", k=ctx["kartes"][0]
        )
        self.assertIn('class="service-logo"', html)
        self.assertIn('src="assets/service-icons/x.png"', html)
        idx = gp.make_env().get_template("karte-index.html.j2").render(
            **ctx, page="karte_index"
        )
        self.assertIn('src="assets/service-icons/x.png"', idx)

    def test_service_icon_assets_are_copied_under_assets_directory(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as out:
            icon = Path(src) / "service-icons" / "x.png"
            icon.parent.mkdir(parents=True)
            icon.write_bytes(b"png-bytes")
            with mock.patch.object(gp, "ASSETS_DIR", Path(src)):
                copied = gp._copy_assets(Path(out))
            self.assertGreaterEqual(copied, 1)
            self.assertEqual(
                (Path(out) / "assets" / "service-icons" / "x.png").read_bytes(),
                b"png-bytes",
            )


class TestBackfillEntityLogos(unittest.TestCase):
    def test_icon_path_rejects_path_traversal_entity_id(self):
        with self.assertRaises(ValueError):
            logos.icon_path_for("../escape")

    def test_official_pages_exclude_known_third_party_sources(self):
        entity = {
            "entity_id": "physical-intelligence",
            "name": "Physical Intelligence",
            "vendor": "Physical Intelligence",
            "history": [
                {
                    "source": "Physical Intelligence",
                    "url": "https://www.pi.website/blog/pi07",
                },
                {
                    "source": "Physical Intelligence",
                    "url": "https://arxiv.org/abs/2410.24164",
                },
            ],
        }
        pages = logos.official_pages(entity)
        self.assertIn("https://www.pi.website/", pages)
        self.assertNotIn("https://arxiv.org/", pages)

    def test_dry_run_discovers_official_candidates_without_writing_jsonl(self):
        entity = {
            "entity_id": "sample",
            "name": "Sample",
            "kind": "app",
            "domain": "code",
            "offering": "commercial",
            "vendor": "Sample Inc.",
            "category": "editor",
            "snapshot_date": "2026-06-08",
            "positioning": "p",
            "history": [{"when": "2026", "title": "公開", "url": "https://example.com/news"}],
        }
        html = (
            b'<html><head><link rel="apple-touch-icon" href="/apple.png">'
            b'<meta property="og:image" content="/og.png"></head></html>'
        )

        def fake_fetch(url: str, *, timeout: int = 15):
            if url.endswith(".png"):
                return b"not-used-in-dry-run", "image/png"
            return html, "text/html"

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "entities.jsonl"
            path.write_text(json.dumps(entity, ensure_ascii=False) + "\n", encoding="utf-8")
            with mock.patch.object(logos, "ENTITIES", path), mock.patch.object(
                logos, "fetch", side_effect=fake_fetch
            ), mock.patch.object(sys, "argv", ["backfill_entity_logos.py", "--dry-run", "--limit", "1"]):
                self.assertEqual(logos.main(), 0)
            loaded = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertNotIn("logo", loaded[0])
