import html.parser
import pathlib
import re
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class DocumentParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.ids = set()
        self.lang = None
        self.title_depth = 0
        self.title_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append(tag)
        if tag == "html":
            self.lang = attrs.get("lang")
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "title":
            self.title_depth += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self.title_depth -= 1

    def handle_data(self, data):
        if self.title_depth:
            self.title_text.append(data)


class WebAssetTests(unittest.TestCase):
    def parse(self, relative):
        parser = DocumentParser()
        parser.feed((ROOT / relative).read_text(encoding="utf-8"))
        return parser

    def test_documents_have_landmarks_language_and_titles(self):
        for relative in ("landing.html", "app/index.html"):
            with self.subTest(relative=relative):
                parser = self.parse(relative)
                self.assertEqual(parser.lang, "en")
                self.assertIn("main", parser.tags)
                self.assertIn("h1", parser.tags)
                self.assertTrue("".join(parser.title_text).strip())

    def test_dashboard_references_existing_local_assets(self):
        html = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
        for path in re.findall(r'(?:src|href)="([^"]+)"', html):
            if path.startswith(("#", "http://", "https://")):
                continue
            self.assertTrue((ROOT / "app" / path).resolve().exists(), path)

    def test_dashboard_javascript_syntax_and_safe_dom_policy(self):
        script = ROOT / "app" / "dashboard.js"
        result = subprocess.run(["node", "--check", str(script)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        source = script.read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", source)
        self.assertNotIn("eval(", source)
        self.assertIn("sameOriginEndpoint", source)

    def test_public_copy_does_not_claim_performance_or_checkout(self):
        combined = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in ("README.md", "landing.html", "app/index.html")
        ).lower()
        for forbidden in ("guaranteed profit", "win rate:", "members earned", "checkout is live"):
            self.assertNotIn(forbidden, combined)
        self.assertIn("not financial advice", combined)
        self.assertIn("no performance claims", combined)


if __name__ == "__main__":
    unittest.main()
