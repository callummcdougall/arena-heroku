# Per-PR website previews

Every pull request to the content repo (`ARENA-education/ARENA_materials`) that
changes a page of this site gets its own rendered copy of that page, with a
side-by-side **diff vs main** view:

```
https://learn.arena.education/pr-preview/pr-<N>/
```

A bot comments that URL on the PR. The idea and the diff view are ported from
[iliad-team/iliad-intensive](https://github.com/iliad-team/iliad-intensive)
(`docs/PR-PREVIEWS.md`, `public/diff.js`); the plumbing is different because
the two sites are built differently.

## How it works

ILIAD's site is a static export, so a preview there is a second build of the
whole site under a path prefix. This site is not built at all: it fetches
markdown from the content repo at request time and renders it. So a preview
here is **the same app, rendering the same URL from different markdown** — no
second deploy, no build step.

The catch is *which* markdown. A content PR edits master files
(`infrastructure/chapters/**/master_*.py`); the pages this site renders
(`chapterX/instructions/pages/*.md`) are regenerated from them only after
merge. A PR's own branch therefore still holds the old pages. Two halves:

**Content repo** (`.github/workflows/` there, documented in its own
`.github/PR-PREVIEWS.md`): the PR check already regenerates the changed sections;
it now uploads the regenerated pages, and a second workflow copies them to a
`pr-preview` branch:

```
pr-preview branch
  pr-407/preview.json                                  {pr, title, head_sha, pages: [...]}
  pr-407/chapter0_fundamentals/instructions/pages/03_[0.3]_Optimization.md
  pr-412/...
```

**This repo**:

| Piece | Where |
|---|---|
| `/pr-preview/pr-<N>/…` routes — the chapter pages and the section API again, with a `pr` argument | `pages/urls.py` |
| `_get_preview()` reads `pr-<N>/preview.json` (404 → no such preview); `_fetch_content()` serves a page from the preview if the manifest lists it, otherwise from main as usual | `pages/views.py` |
| `preview_index` — landing page listing the pages the PR changes | `pages/views.py`, `templates/preview_index.html` |
| Banner, `noindex`, `window.ARENA_BASE_PATH`; `{{ base_path }}` on in-site links so navigation stays inside the preview | `templates/base.html`, `templates/chapter.html` |
| `BASE_PATH` on the URLs chapter-nav builds, and an `arena:content-rendered` event after each client-side render | `static/js/chapter-nav.js` |
| The diff view | `static/js/diff.js`, end of `static/css/style.css` |

Outside `/pr-preview/` none of it is active: `base_path` renders as an empty
string, and the banner, the script tag and `diff.js` itself are only emitted
when the view passes a `preview`.

### The diff view

Tick **diff vs main** in the banner. `diff.js` fetches the current section
from the section API twice — `/pr-preview/pr-<N>/api/<chapter>/<section>/` and
`/api/<chapter>/<section>/` — and takes the current subsection from each. Both
are this origin and both return rendered HTML, so there is nothing to scrape.

From there it is ILIAD's algorithm unchanged: split both articles into leaf
blocks, sequence-diff them (LCS), pair removed+added blocks that share enough
words into edits with word-level marks inside (an inline formula is one
token; KaTeX's MathML annotation supplies the TeX source), then pad matched
blocks into shared rows so the two columns scroll together. Solutions
(`<details>`) that contain a change are opened. **sync scroll** off gives each
column its own scrollbar.

The site navigates client-side, so the view listens for
`arena:content-rendered` and rebuilds itself for each subsection. The status
readout (`−1 +4 ~1 blocks`) is per subsection; a subsection that does not
exist on main reports "subsection is new on this PR".

## Configuration

Nothing is required in production: previews are read from the `pr-preview`
branch of the repo that `GH_OWNER` / `GH_REPO` already name.

| Env var | Default | |
|---|---|---|
| `PR_PREVIEW_BRANCH` | `pr-preview` | branch of the content repo holding previews |
| `PR_PREVIEW_RAW_BASE` | *(unset)* | full base URL to read previews from instead, e.g. a local server |

### Trying it locally

Serve a fake `pr-preview` branch and point the app at it:

```sh
mkdir -p fake/pr-1/chapter0_fundamentals/instructions/pages
# ...put an edited copy of a page in there, plus fake/pr-1/preview.json:
#   {"pr": 1, "title": "test", "pages": ["chapter0_fundamentals/instructions/pages/01_[0.1]_Ray_Tracing.md"]}
python3 -m http.server 8901 --directory fake &
PR_PREVIEW_RAW_BASE=http://127.0.0.1:8901 python3 manage.py runserver
# open http://127.0.0.1:8000/pr-preview/pr-1/
```

`http.server` sends `.md` without a charset, which turns non-ASCII text into
mojibake (GitHub sends UTF-8); if that matters, serve with
`Content-Type: text/plain; charset=utf-8`.

Tests: `python3 manage.py test pages`.

## Security

A preview is PR-author-controlled markdown — which may contain raw HTML —
rendered on this site's origin. That is why the app reads previews **only**
from the `pr-preview` branch, which only the content repo's workflow writes,
and only for authors it trusts (members and collaborators, or any PR a
maintainer has given the `preview` label). Do not "simplify" this to reading `refs/pull/<N>/head`
directly: raw.githubusercontent.com does serve it, but that would render
markdown from anyone who opens a PR.

PR titles reach the page through Django's autoescaping; keep them out of
`|safe`.

## Known limitations

- **The chapter list comes from main.** `config.yaml` is not previewed, so a PR
  that adds, renames or reorders sections shows main's navigation.
- **Only the pages.** The right sidebar's download / copy-context / chat
  features read `/api/raw/…`, i.e. main's files, even inside a preview.
- **Freshness.** raw.githubusercontent.com caches for about five minutes, and
  this app's responses carry `max-age=300`; a push can take that long to show.
- **Blocks are matched by content**, so inserting an exercise mid-section shows
  later renumbered headings as edited (true, but noisy). A solution with a
  removed sentence opens on the left only.
- **Alignment is measured, not computed**: a very late-loading image can leave
  a few px of drift; there is a second pass after 1.5 s.
