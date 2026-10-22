import json
import re
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

COLAB = "https://colab.research.google.com/github/ARENA-education/ARENA_materials/blob"
RAYS_NOTEBOOK = "ch0/exercises/part1_ray_tracing/0.1_Ray_Tracing_exercises.ipynb"
CNNS_NOTEBOOK = "ch0/exercises/part2_cnns/0.2_CNNs_exercises.ipynb"

MANIFEST = {
    "pr": 7,
    "title": "Fix <b>rays</b>",
    "head_sha": "abc1234def",
    "pages": ["ch0/instructions/pages/01.md"],
    "notebooks": [RAYS_NOTEBOOK],
}


def fake_fetch_text(url: str) -> str:
    """Stand-in for GitHub: main has both pages, the pr-preview branch has PR 7's copy of 01.md."""
    if url.endswith("/pr-7/preview.json"):
        return json.dumps(MANIFEST)
    if url.endswith("/pr-7/ch0/instructions/pages/01.md"):
        return (
            "# Rays\n\nText from the pull request.\n\n"
            f"[exercises]({COLAB}/main/{RAYS_NOTEBOOK}?t=20260928) | [cnns]({COLAB}/main/{CNNS_NOTEBOOK}?t=20260928)"
        )
    if "/pr-" in url:
        raise Http404(url)
    if url.endswith("/refs/heads/main/ch0/instructions/pages/01.md"):
        return f"# Rays\n\nText from main.\n\n[exercises]({COLAB}/main/{RAYS_NOTEBOOK}?t=20260901)"
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

    def test_colab_links_open_the_prs_notebooks(self, *_):
        for url in ("/pr-preview/pr-7/ch0/01_ray_tracing/", "/pr-preview/pr-7/api/ch0/01_ray_tracing/"):
            html = self.client.get(url).content.decode()
            self.assertIn(f"{COLAB}/pr-preview/pr-7/{RAYS_NOTEBOOK}?t=abc1234", html)
            self.assertNotIn(f"{COLAB}/main/{RAYS_NOTEBOOK}", html)
            # A notebook the PR did not regenerate is still main's.
            self.assertIn(f"{COLAB}/main/{CNNS_NOTEBOOK}?t=20260928", html)

    def test_preview_without_notebooks_keeps_mains_colab_links(self, *_):
        manifest = {k: v for k, v in MANIFEST.items() if k != "notebooks"}
        with mock.patch.dict(MANIFEST, manifest, clear=True):
            html = self.client.get("/pr-preview/pr-7/ch0/01_ray_tracing/").content.decode()
        self.assertIn(f"{COLAB}/main/{RAYS_NOTEBOOK}?t=20260928", html)

    def test_unknown_pr_is_a_404(self, *_):
        self.assertEqual(self.client.get("/pr-preview/pr-8/").status_code, 404)
        self.assertEqual(self.client.get("/pr-preview/pr-8/ch0/01_ray_tracing/").status_code, 404)
        self.assertEqual(self.client.get("/pr-preview/pr-8/api/ch0/01_ray_tracing/").status_code, 404)

    def test_live_site_has_no_preview_markup(self, *_):
        html = self.client.get("/ch0/01_ray_tracing/").content.decode()
        self.assertIn("Text from main.", html)
        self.assertIn('href="/ch0/02_cnns/"', html)
        self.assertIn(f"{COLAB}/main/{RAYS_NOTEBOOK}?t=20260901", html)
        for marker in ("preview-banner", "js/diff.js", "ARENA_BASE_PATH =", "noindex"):
            self.assertNotIn(marker, html)


class DetailsBlockTests(SimpleTestCase):
    """`<details>` dropdowns, including dropdowns nested inside a dropdown."""

    NESTED = (
        "<details>\n<summary>Outer</summary>\n\nOuter **before**.\n\n"
        "<details>\n<summary>Inner</summary>\n\nInner **bold**.\n</details>\n\n"
        "Outer **after**.\n</details>\n\nAfter the dropdown.\n"
    )

    def outermost_details(self, html: str) -> str:
        """The first <details> element of `html`, matched by nesting depth."""
        depth = 0
        for m in re.finditer(r"<(/?)details\b[^>]*>", html):
            depth += -1 if m.group(1) else 1
            if depth == 0:
                return html[: m.end()]
        self.fail(f"unclosed <details> in {html!r}")

    def test_nested_dropdown_stays_inside_its_parent(self):
        html = views._render_markdown(self.NESTED)
        self.assertEqual(html.count("<details>"), 2)
        self.assertEqual(html.count("</details>"), 2)
        outer = self.outermost_details(html[html.index("<details>"):])
        # The parent's text after the inner dropdown is still inside the parent, as its own paragraph (the
        # parent's </details> used to end up inside that paragraph: "<p>Outer ... </details></p>")...
        self.assertIn("<p>Outer <strong>after</strong>.</p>", outer)
        self.assertNotIn("</details></p>", html)
        # ...and the page text after the dropdown is not.
        self.assertNotIn("After the dropdown.", outer)
        self.assertIn("<p>After the dropdown.</p>", html)

    def test_markdown_inside_a_nested_dropdown_is_rendered(self):
        html = views._render_markdown(self.NESTED)
        self.assertIn("Inner <strong>bold</strong>.", html)
        self.assertNotIn("**", html)
        self.assertNotIn("DETAILSBLOCK", html)

    def test_single_dropdown(self):
        html = views._render_markdown("<details>\n<summary>Hint</summary>\n\nUse **this**.\n</details>\n")
        self.assertIn("<summary>Hint</summary>", html)
        self.assertIn("Use <strong>this</strong>.", html)
        self.assertEqual(html.count("</details>"), 1)

    def test_unclosed_dropdown_runs_to_the_end(self):
        html = views._render_markdown("<details>\n<summary>Oops</summary>\n\nNo **closing** tag.\n")
        self.assertIn("No <strong>closing</strong> tag.", html)
        self.assertEqual(html.count("</details>"), 1)
        self.assertNotIn("DETAILSBLOCK", html)

    def test_dropdowns_after_an_unclosed_one_are_still_rendered(self):
        text = (
            "<details>\n<summary>Never closed</summary>\n\nOops.\n\n"
            "<details>\n<summary>Later</summary>\n\nLater **bold**.\n</details>\n"
        )
        html = views._render_markdown(text)
        self.assertIn("Later <strong>bold</strong>.", html)
        self.assertEqual(html.count("<details>"), html.count("</details>"))
