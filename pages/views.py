import html
import json
import os
import re
import uuid

import markdown as md
import requests
import tiktoken
from django.http import Http404, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from openai import OpenAI
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer, TextLexer

from pathlib import Path

from .chapters import get_all_chapters, get_chapter, get_section

# Directory for local content files (group overview pages)
CONTENT_DIR = Path(__file__).parent / "content"

# Initialize tiktoken encoder (cl100k_base is used by GPT-4, Claude, etc.)
_tiktoken_encoder = tiktoken.get_encoding("cl100k_base")

# Delimiter for sub-sections within a markdown file
SUBSECTION_DELIMITER = "=== NEW CHAPTER ==="


def _raw_url(md_path: str) -> str:
    """Construct GitHub raw content URL for a markdown file."""
    owner = os.environ.get("GH_OWNER", "callummcdougall")
    # repo = os.environ.get("GH_REPO", "ARENA_3.0")
    repo = os.environ.get("GH_REPO", "arena-pragmatic-interp")
    branch = os.environ.get("GH_BRANCH", "main")
    return f"https://raw.githubusercontent.com/{owner}/{repo}/refs/heads/{branch}/{md_path}"


def _fetch_text(url: str) -> str:
    """Fetch text content from a URL."""
    headers = {}
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
    r = requests.get(url, headers=headers, timeout=10)
    if r.status_code == 404:
        raise Http404("Content not found")
    r.raise_for_status()
    return r.text


def _read_local_content(filename: str) -> str:
    """Read markdown content from local content directory."""
    filepath = CONTENT_DIR / filename
    if not filepath.exists():
        raise Http404(f"Local content not found: {filename}")
    return filepath.read_text(encoding="utf-8")


def _preprocess_exercise_blocks(text: str) -> str:
    """
    Pre-process markdown text to transform exercise info blocks.

    These blocks look like:
    > ```yaml
    > Difficulty: 🔴🔴⚪⚪⚪
    > Importance: 🔵🔵🔵⚪⚪
    >
    > You should spend up to 10-15 minutes on this exercise.
    > ```

    We convert them to HTML divs that will pass through markdown rendering.
    """
    # Pattern to match the blockquote with yaml code block containing Difficulty/Importance
    # The > prefix on each line makes this a blockquote, and ```yaml...``` is a code block
    pattern = r">\s*```yaml\n((?:>.*\n)*?)>\s*```"

    def replace_block(match):
        content = match.group(1)
        # Remove the > prefix from each line
        lines = [line.lstrip(">").strip() for line in content.split("\n")]

        difficulty = ""
        importance = ""
        description_lines = []

        for line in lines:
            if line.startswith("Difficulty:"):
                difficulty = line.replace("Difficulty:", "").strip()
            elif line.startswith("Importance:"):
                importance = line.replace("Importance:", "").strip()
            elif line:
                description_lines.append(line)

        description = " ".join(description_lines)

        # Return HTML that will pass through markdown
        html = f"""<div class="exercise-info">
<div class="exercise-info-row">
<span class="exercise-info-label">Difficulty:</span>
<span class="exercise-info-value">{difficulty}</span>
</div>
<div class="exercise-info-row">
<span class="exercise-info-label">Importance:</span>
<span class="exercise-info-value">{importance}</span>
</div>
{f'<div class="exercise-info-description">{description}</div>' if description else ""}
</div>"""
        return html

    return re.sub(pattern, replace_block, text, flags=re.MULTILINE)


def _protect_latex(text: str) -> tuple[str, dict]:
    """
    Protect LaTeX blocks from markdown processing by replacing with placeholders.
    Returns the modified text and a dict mapping placeholders to original LaTeX.
    """
    placeholders = {}

    # Protect display math blocks ($$...$$) - these may span multiple lines
    def replace_display(match):
        placeholder = f"LATEXDISPLAY{uuid.uuid4().hex}ENDLATEX"
        # Wrap in a div with class for proper styling
        content = match.group(1)
        placeholders[placeholder] = f'<div class="katex-display-wrapper">$${content}$$</div>'
        return placeholder

    text = re.sub(r"\$\$([\s\S]*?)\$\$", replace_display, text)

    # Protect inline math ($...$) - but not $$ which we already handled
    def replace_inline(match):
        placeholder = f"LATEXINLINE{uuid.uuid4().hex}ENDLATEX"
        content = match.group(1)
        placeholders[placeholder] = f"${content}$"
        return placeholder

    # Match $ ... $ but not $$ and not escaped \$
    text = re.sub(r"(?<!\$)\$(?!\$)([^\$\n]+?)\$(?!\$)", replace_inline, text)

    return text, placeholders


def _restore_latex(html_text: str, placeholders: dict) -> str:
    """Restore LaTeX blocks from placeholders."""
    for placeholder, latex in placeholders.items():
        html_text = html_text.replace(placeholder, latex)
        # Also handle case where markdown might have wrapped it in <p> tags
        html_text = html_text.replace(f"<p>{placeholder}</p>", latex)
    return html_text


def _highlight_code(code: str, lang: str) -> str:
    """Highlight code using Pygments."""
    try:
        if lang:
            lexer = get_lexer_by_name(lang, stripall=True)
        else:
            lexer = guess_lexer(code)
    except Exception:
        lexer = TextLexer()

    formatter = HtmlFormatter(nowrap=True)
    highlighted = highlight(code, lexer, formatter)
    return f'<div class="codehilite"><pre>{highlighted}</pre></div>'


def _process_details_content(text: str) -> str:
    """
    Pre-process <details> blocks to ensure markdown inside them is rendered.

    Markdown doesn't process content inside HTML tags, so we need to:
    1. Extract content from <details> blocks
    2. Process that content as markdown
    3. Reconstruct the details block with rendered content
    """
    def render_details_block(match):
        full_match = match.group(0)
        # Extract the summary line
        summary_match = re.search(r'<summary>(.*?)</summary>', full_match, re.DOTALL)
        if not summary_match:
            return full_match

        summary = summary_match.group(0)
        # Get content after summary and before </details>
        content_start = full_match.find('</summary>') + len('</summary>')
        content_end = full_match.rfind('</details>')
        if content_end == -1:
            return full_match

        content = full_match[content_start:content_end].strip()

        # Process the content as markdown (basic inline formatting)
        # Handle code blocks first (``` ... ```) with Pygments highlighting
        code_blocks = {}
        def protect_code_block(m):
            placeholder = f"CODEBLOCK{uuid.uuid4().hex}END"
            lang = m.group(1) or "python"
            code = m.group(2)
            code_blocks[placeholder] = _highlight_code(code, lang)
            return placeholder

        content = re.sub(r'```(\w*)\n(.*?)```', protect_code_block, content, flags=re.DOTALL)

        # Handle inline code
        content = re.sub(r'`([^`]+)`', r'<code>\1</code>', content)
        # Handle bold
        content = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', content)
        # Handle italic (but not inside code blocks or after *)
        content = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', content)

        # Restore code blocks
        for placeholder, code_html in code_blocks.items():
            content = content.replace(placeholder, code_html)

        # Wrap paragraphs (simple heuristic: split by double newline)
        paragraphs = content.split('\n\n')
        processed_paragraphs = []
        for p in paragraphs:
            p = p.strip()
            if p and not p.startswith('<'):
                p = f'<p>{p}</p>'
            processed_paragraphs.append(p)
        content = '\n'.join(processed_paragraphs)

        return f'<details>\n{summary}\n{content}\n</details>'

    # Match <details>...</details> blocks
    text = re.sub(r'<details>.*?</details>', render_details_block, text, flags=re.DOTALL)
    return text


def _render_markdown(text: str) -> str:
    """Convert markdown text to HTML."""
    # Pre-process to handle exercise info blocks
    text = _preprocess_exercise_blocks(text)

    # Protect LaTeX blocks from markdown processing
    text, latex_placeholders = _protect_latex(text)

    # Configure markdown with proper syntax highlighting
    # Note: codehilite must come BEFORE fenced_code for proper integration
    rendered = md.markdown(
        text,
        extensions=[
            "codehilite",
            "fenced_code",
            "tables",
            "toc",
        ],
        extension_configs={
            "codehilite": {
                "css_class": "codehilite",
                "guess_lang": True,
                "linenums": False,
                "use_pygments": True,
            },
        },
    )

    # Restore LaTeX blocks
    rendered = _restore_latex(rendered, latex_placeholders)

    # Post-process details blocks to render markdown inside them
    rendered = _process_details_content(rendered)

    return rendered


def _extract_title_from_markdown(text: str) -> str:
    """Extract the first h1 title from markdown text."""
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "Untitled"


def _extract_headers_from_html(html_content: str) -> list[dict]:
    """Extract headers from rendered HTML for table of contents."""
    headers = []
    # Match h1-h4 headers with their id attributes
    pattern = r'<h([1-4])[^>]*id="([^"]*)"[^>]*>(.+?)</h\1>'
    for match in re.finditer(pattern, html_content, re.DOTALL):
        level = int(match.group(1))
        header_id = match.group(2)
        # Strip HTML tags from title and decode HTML entities
        title = re.sub(r"<[^>]+>", "", match.group(3)).strip()
        title = html.unescape(title)  # Decode &amp; -> &, etc.
        headers.append(
            {
                "level": level,
                "id": header_id,
                "title": title,
            }
        )
    return headers


def _slugify(text: str) -> str:
    """Create a URL-safe slug from text."""
    # Remove emoji and special characters, lowercase, replace spaces with hyphens
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[-\s]+", "-", slug).strip("-")
    return slug


def _parse_subsections(markdown_text: str) -> list[dict]:
    """
    Parse a markdown file into sub-sections based on the === NEW CHAPTER === delimiter.
    Returns a list of dicts with id, title, markdown, and html for each sub-section.
    """
    parts = markdown_text.split(SUBSECTION_DELIMITER)
    subsections = []

    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue

        title = _extract_title_from_markdown(part)
        rendered_html = _render_markdown(part)
        headers = _extract_headers_from_html(rendered_html)

        # Create a slug for the subsection
        if i == 0:
            slug = "intro"
            display_title = "Introduction"  # Always show "Introduction" for first subsection
        else:
            slug = _slugify(title) or f"section-{i}"
            display_title = title

        subsections.append(
            {
                "index": i,
                "id": slug,
                "title": display_title,
                "html": rendered_html,
                "headers": headers,
            }
        )

    return subsections


def _get_context_base() -> dict:
    """Get base context with chapters list."""
    return {
        "chapters": get_all_chapters(),
    }


@require_GET
def home(request):
    """Homepage view - displays chapter cards."""
    context = _get_context_base()
    return render(request, "home.html", context)


@require_GET
def faq(request):
    """FAQ page."""
    context = _get_context_base()
    # Read and render the FAQ markdown
    markdown_content = _read_local_content("faq.md")
    rendered_html = _render_markdown(markdown_content)
    context["content"] = rendered_html
    return render(request, "faq.html", context)


@require_GET
def setup(request):
    """Setup instructions page."""
    context = _get_context_base()
    # Read and render the setup instructions markdown
    markdown_content = _read_local_content("setup_instructions.md")
    rendered_html = _render_markdown(markdown_content)
    context["content"] = rendered_html
    return render(request, "setup.html", context)


@require_GET
def map_view(request):
    """Map page - dependency map of course sections."""
    context = _get_context_base()
    # Pass chapters as JSON for JavaScript to render the map
    context["chapters_json"] = json.dumps(context["chapters"])
    return render(request, "map.html", context)


@require_GET
def chapter_view(request, chapter_id: str, section_id: str | None = None, subsection_id: str | None = None):
    """
    Main chapter view - handles full page loads.
    Renders the chapter template with initial section content.
    JavaScript handles subsequent navigation within the chapter.
    """
    chapter = get_chapter(chapter_id)
    if not chapter:
        raise Http404("Chapter not found")

    # If no section specified, show chapter overview
    if not section_id:
        context = _get_context_base()
        context.update(
            {
                "chapter": {"id": chapter_id, **chapter},
                "current_chapter": chapter_id,
                "current_section": None,
                "current_subsection": None,
                "content": None,
                "subsections": None,
                "chapter_json": json.dumps({"id": chapter_id, **chapter}),
            }
        )
        return render(request, "chapter.html", context)

    section = get_section(chapter_id, section_id)
    if not section:
        raise Http404("Section not found")

    # Fetch and parse markdown content
    try:
        # Check if this is a local content file (group overview) or remote
        if section.get("local_path"):
            text = _read_local_content(section["local_path"])
        else:
            text = _fetch_text(_raw_url(section["path"]))
        subsections = _parse_subsections(text)
    except Http404:
        subsections = [
            {
                "index": 0,
                "id": "intro",
                "title": section["title"],
                "html": f"<p>Content for '{section['title']}' is not yet available.</p>",
                "headers": [],
            }
        ]
    except requests.RequestException as e:
        subsections = [
            {
                "index": 0,
                "id": "error",
                "title": "Error",
                "html": f"<p>Error loading content: {e}</p>",
                "headers": [],
            }
        ]

    # Determine current subsection
    current_subsection = subsection_id or (subsections[0]["id"] if subsections else None)

    # Find the current subsection's content
    current_subsection_data = next(
        (s for s in subsections if s["id"] == current_subsection), subsections[0] if subsections else None
    )

    context = _get_context_base()
    context.update(
        {
            "chapter": {"id": chapter_id, **chapter},
            "current_chapter": chapter_id,
            "current_section": section_id,
            "current_subsection": current_subsection,
            "section": section,
            "subsections": subsections,
            "current_subsection_data": current_subsection_data,
            # Pass data to JavaScript for client-side navigation
            "chapter_json": json.dumps({"id": chapter_id, **chapter}),
            "subsections_json": json.dumps(subsections),
        }
    )
    return render(request, "chapter.html", context)


@require_GET
def section_api(request, chapter_id: str, section_id: str):
    """
    API endpoint to fetch section content as JSON.
    Used by JavaScript for client-side navigation.
    """
    chapter = get_chapter(chapter_id)
    if not chapter:
        return JsonResponse({"error": "Chapter not found"}, status=404)

    section = get_section(chapter_id, section_id)
    if not section:
        return JsonResponse({"error": "Section not found"}, status=404)

    # Fetch and parse markdown content
    try:
        # Check if this is a local content file (group overview) or remote
        if section.get("local_path"):
            text = _read_local_content(section["local_path"])
        else:
            text = _fetch_text(_raw_url(section["path"]))
        subsections = _parse_subsections(text)
    except Http404:
        subsections = [
            {
                "index": 0,
                "id": "intro",
                "title": section["title"],
                "html": f"<p>Content for '{section['title']}' is not yet available.</p>",
                "headers": [],
            }
        ]
    except requests.RequestException as e:
        subsections = [
            {
                "index": 0,
                "id": "error",
                "title": "Error",
                "html": f"<p>Error loading content: {e}</p>",
                "headers": [],
            }
        ]

    return JsonResponse(
        {
            "section": section,
            "subsections": subsections,
        }
    )


@csrf_exempt
@require_POST
def token_count_api(request):
    """
    API endpoint to count tokens in text using tiktoken.
    Accepts JSON body with 'text' field.
    Returns token count.
    """
    try:
        data = json.loads(request.body)
        text = data.get("text", "")

        if not text:
            return JsonResponse({"tokens": 0})

        tokens = _tiktoken_encoder.encode(text)
        return JsonResponse({"tokens": len(tokens)})

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# System prompt for the chat assistant
CHAT_SYSTEM_PROMPT = """You are a teaching assistant for the ARENA (Alignment Research Engineer Accelerator) program.

Response style:
- Be extremely concise. Give the shortest answer that fully addresses the question.
- No preamble, no filler phrases like "Great question!" or "I'd be happy to help"
- No unnecessary caveats or hedging unless genuinely uncertain
- Use code snippets and bullet points over prose when possible
- If a one-sentence answer suffices, give a one-sentence answer
- Reference specific line numbers or function names from the context when relevant

{context_section}"""


def _stream_chat_response(messages: list, model: str):
    """Generator that streams chat responses from OpenAI."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        yield "Error: OPENAI_API_KEY environment variable not set"
        return

    try:
        client = OpenAI(api_key=api_key)

        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    except Exception as e:
        yield f"Error: {str(e)}"


@require_GET
def static_context_api(request):
    """
    API endpoint to get static page content for chat context.
    Returns the content of faq.md, setup_instructions.md, homepage_info.md,
    and a summary of all chapters and sections from config.yaml
    for use as chat context when not on a chapter page.
    """
    try:
        content_parts = []

        # Add course structure summary from chapters
        chapters = get_all_chapters()
        if chapters:
            course_summary = "## ARENA Course Structure\n\n"
            course_summary += "ARENA (Alignment Research Engineer Accelerator) is a comprehensive curriculum covering:\n\n"
            for chapter in chapters:
                course_summary += f"### {chapter['title']}\n"
                course_summary += f"{chapter['description']}\n\n"
                course_summary += "**Sections:**\n"
                for section in chapter.get("sections", []):
                    if not section.get("is_group"):
                        number = section.get("number", "")
                        title = section.get("title", "")
                        desc = section.get("streamlit_description", "")
                        if number:
                            course_summary += f"- **{number} {title}**: {desc}\n"
                        else:
                            course_summary += f"- **{title}**: {desc}\n"
                course_summary += "\n"
            content_parts.append(course_summary)

        # Read each static content file
        for filename in ["homepage_info.md", "setup_instructions.md", "faq.md"]:
            try:
                file_content = _read_local_content(filename)
                content_parts.append(f"## {filename}\n\n{file_content}")
            except Http404:
                continue

        combined_content = "\n\n---\n\n".join(content_parts)
        return JsonResponse({"content": combined_content})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_POST
def chat_api(request):
    """
    API endpoint for chat with streaming responses.
    Accepts JSON body with:
    - messages: list of {role, content} message objects
    - context: optional context string to include in system prompt
    - model: model to use (default: gpt-4.1-mini)
    """
    try:
        data = json.loads(request.body)
        messages = data.get("messages", [])
        context = data.get("context", "")
        model = data.get("model", "gpt-4.1-mini")

        if not messages:
            return JsonResponse({"error": "No messages provided"}, status=400)

        # Build system prompt with context
        if context:
            context_section = f"The following context has been provided:\n\n{context}"
        else:
            context_section = "No specific context has been provided."

        system_prompt = CHAT_SYSTEM_PROMPT.format(context_section=context_section)

        # Build full message list with system prompt
        full_messages = [{"role": "system", "content": system_prompt}]
        full_messages.extend(messages)

        # Return streaming response
        response = StreamingHttpResponse(
            _stream_chat_response(full_messages, model), content_type="text/plain; charset=utf-8"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
