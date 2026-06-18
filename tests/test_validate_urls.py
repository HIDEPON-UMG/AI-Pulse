import unittest

import tools.validate_urls as vu


class TestValidateUrls(unittest.TestCase):
    def test_ai_meta_400_is_ambiguous_but_other_400_stays_fatal(self):
        """ai.meta.com は実在 URL でも 400 を返すことがあるため、host 限定で ambiguous OK にする。"""
        original_probe = vu._probe
        calls = []

        def fake_probe(url, *, method, timeout, range_header, ua):
            calls.append((url, method, range_header))
            return 400, f"{method}[stub] 400"

        vu._probe = fake_probe
        try:
            meta = vu._verify_one(
                vu.UrlRef("https://ai.meta.com/blog/llama-4-multimodal-intelligence/", "meta"),
                timeout=0.01,
            )
            other = vu._verify_one(
                vu.UrlRef("https://example.com/bad-request", "other"),
                timeout=0.01,
            )
        finally:
            vu._probe = original_probe

        self.assertTrue(meta.ok)
        self.assertIn("anti-bot", meta.detail)
        self.assertFalse(other.ok)
        self.assertEqual(other.status, 400)
        self.assertEqual(len(calls), 6)
