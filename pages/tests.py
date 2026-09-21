import json
from unittest import mock

from django.http import Http404
from django.test import SimpleTestCase, override_settings

from . import views

CHAPTER = {
    "title": "Fundamentals",
    "short_title": "Fundamentals",
    "short_description": "",
    "description": "",
    "color": "#000000",
    "icon": "book",
    "header_image": "",
    "sections": [
        {"id": "01_ray_tracing", "number": "0.1", "title": "Ray Tracing", "path": "ch0/instructions/pages/01.md"},
        {"id": "02_cnns", "number": "0.2", "title": "CNNs", "path": "ch0/instructions/pages/02.md"},
    ],
}

MANIFEST = {"pr": 7, "title": "Fix <b>rays</b>", "head_sha": "abc", "pages": ["ch0/instructions/pages/01.md"]}


def fake_fetch_text(url: str) -> str:
    """Stand-in for GitHub: main has both pages, the pr-preview branch has PR 7's copy of 01.md."""
    if url.endswith("/pr-7/preview.json"):
        return json.dumps(MANIFEST)
    if url.endswith("/pr-7/ch0/instructions/pages/01.md"):
        return "# Rays\n\nText from the pull request."
    if "/pr-" in url:
        raise Http404(url)
    if url.endswith("/refs/heads/main/ch0/instructions/pages/01.md"):
        return "# Rays\n\nText from main."
    if url.endswith("/refs/heads/main/ch0/instructions/pages/02.md"):
        return "# CNNs\n\nUntouched page."
    raise Http404(url)


# The manifest storage needs `collectstatic` output; tests render without it.
PLAIN_STATIC = {"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}


@override_settings(STORAGES=PLAIN_STATIC)
@mock.patch.object(views, "_try_read_local_arena", return_value=None)
@mock.patch.object(views, "_fetch_text", side_effect=fake_fetch_text)
@mock.patch.object(views, "get_all_chapters", return_value=[{"id": "ch0", "section_count": 2, **CHAPTER}])
@mock.patch.object(views, "get_section", side_effect=lambda c, s: next((x for x in CHAPTER["sections"] if x["id"] == s), None))
@mock.patch.object(views, "get_chapter", side_effect=lambda c: CHAPTER if c == "ch0" else None)
class PrPreviewTests(SimpleTestCase):
    def test_changed_page_comes_from_the_preview(self, *_):
        html = self.client.get("/pr-preview/pr-7/ch0/01_ray_tracing/").content.decode()
        self.assertIn("Text from the pull request.", html)
        self.assertNotIn("Text from main.", html)

    def test_untouched_page_is_the_same_as_main(self, *_):
        html = self.client.get("/pr-preview/pr-7/ch0/02_cnns/").content.decode()
        self.assertIn("Untouched page.", html)

    def test_section_api_has_a_preview_twin(self, *_):
        preview = self.client.get("/pr-preview/pr-7/api/ch0/01_ray_tracing/").json()
        live = self.client.get("/api/ch0/01_ray_tracing/").json()
        self.assertIn("Text from the pull request.", preview["subsections"][0]["html"])
        self.assertIn("Text from main.", live["subsections"][0]["html"])

    def test_links_stay_inside_the_preview(self, *_):
        html = self.client.get("/pr-preview/pr-7/ch0/01_ray_tracing/").content.decode()
        self.assertIn('href="/pr-preview/pr-7/ch0/02_cnns/"', html)
        self.assertIn('window.ARENA_BASE_PATH = "/pr\\u002Dpreview/pr\\u002D7"', html)
        self.assertIn("js/diff.js", html)
        self.assertIn("noindex", html)

    def test_pr_title_is_escaped(self, *_):
        html = self.client.get("/pr-preview/pr-7/ch0/01_ray_tracing/").content.decode()
        self.assertIn("Fix &lt;b&gt;rays&lt;/b&gt;", html)
        self.assertNotIn("Fix <b>rays</b>", html)

    def test_index_lists_the_changed_pages(self, *_):
        html = self.client.get("/pr-preview/pr-7/").content.decode()
        self.assertIn('href="/pr-preview/pr-7/ch0/01_ray_tracing/"', html)
        self.assertNotIn("/pr-preview/pr-7/ch0/02_cnns/", html)

    def test_unknown_pr_is_a_404(self, *_):
        self.assertEqual(self.client.get("/pr-preview/pr-8/").status_code, 404)
        self.assertEqual(self.client.get("/pr-preview/pr-8/ch0/01_ray_tracing/").status_code, 404)
        self.assertEqual(self.client.get("/pr-preview/pr-8/api/ch0/01_ray_tracing/").status_code, 404)

    def test_live_site_has_no_preview_markup(self, *_):
        html = self.client.get("/ch0/01_ray_tracing/").content.decode()
        self.assertIn("Text from main.", html)
        self.assertIn('href="/ch0/02_cnns/"', html)
        for marker in ("preview-banner", "js/diff.js", "ARENA_BASE_PATH =", "noindex"):
            self.assertNotIn(marker, html)
