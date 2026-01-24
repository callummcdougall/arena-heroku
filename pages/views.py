import os
import re

import markdown as md
import requests
from django.http import Http404, HttpResponse
from django.views.decorators.http import require_GET

SAFE_SLUG_RE = re.compile(r"^[a-zA-Z0-9/_\-\.]+$")


def _raw_url(md_path: str) -> str:
    owner = os.environ["GH_OWNER"]
    repo = os.environ["GH_REPO"]
    branch = os.environ.get("GH_BRANCH", "main")
    base = os.environ.get("GH_BASE_PATH", "").strip("/")
    if base:
        md_path = f"{base}/{md_path}"
    md_path = md_path.lstrip("/")
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{md_path}"


def _fetch_text(url: str) -> str:
    headers = {}
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
    r = requests.get(url, headers=headers, timeout=10)
    if r.status_code == 404:
        raise Http404("Not found")
    r.raise_for_status()
    return r.text


@require_GET
def page(request, path="index") -> HttpResponse:
    # Map / -> index.md and /foo/bar -> foo/bar.md
    if not path:
        path = "index"
    if not SAFE_SLUG_RE.match(path) or ".." in path:
        raise Http404("Invalid path")

    md_path = path if path.endswith(".md") else f"{path}.md"
    text = _fetch_text(_raw_url(md_path))
    html = md.markdown(text, extensions=["fenced_code", "tables", "toc"])
    return HttpResponse(html)
