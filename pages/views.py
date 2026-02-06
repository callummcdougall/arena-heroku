import html
import io
import json
import os
import re
import uuid
import zipfile
from pathlib import Path

import markdown as md
import requests
import tiktoken
from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from openai import OpenAI
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name, guess_lexer

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
    print(f"[DEBUG] Fetching URL: {url}")
    r = requests.get(url, headers=headers, timeout=10)
    print(f"[DEBUG] Response status: {r.status_code}")
    if r.status_code == 404:
        print(f"[DEBUG] 404 Not Found for URL: {url}")
        raise Http404(f"Content not found: {url}")
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
        summary_match = re.search(r"<summary>(.*?)</summary>", full_match, re.DOTALL)
        if not summary_match:
            return full_match

        summary = summary_match.group(0)
        # Get content after summary and before </details>
        content_start = full_match.find("</summary>") + len("</summary>")
        content_end = full_match.rfind("</details>")
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

        content = re.sub(r"```(\w*)\n(.*?)```", protect_code_block, content, flags=re.DOTALL)

        # Handle inline code
        content = re.sub(r"`([^`]+)`", r"<code>\1</code>", content)
        # Handle bold
        content = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", content)
        # Handle italic (but not inside code blocks or after *)
        content = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", content)

        # Restore code blocks
        for placeholder, code_html in code_blocks.items():
            content = content.replace(placeholder, code_html)

        # Process content blocks (paragraphs and lists)
        paragraphs = content.split("\n\n")
        processed_paragraphs = []
        for p in paragraphs:
            p = p.strip()
            if not p:
                continue
            # Check if this is a bullet list (lines starting with "- ")
            lines = p.split("\n")
            if all(line.strip().startswith("- ") or line.strip() == "" for line in lines if line.strip()):
                # Convert bullet list to HTML
                list_items = []
                for line in lines:
                    line = line.strip()
                    if line.startswith("- "):
                        list_items.append(f"<li>{line[2:]}</li>")
                if list_items:
                    p = f"<ul>{''.join(list_items)}</ul>"
            # Check if this is a numbered list (lines starting with "1. ", "2. ", etc.)
            elif all(re.match(r"^\d+\.\s", line.strip()) or line.strip() == "" for line in lines if line.strip()):
                list_items = []
                for line in lines:
                    line = line.strip()
                    if re.match(r"^\d+\.\s", line):
                        item_text = re.sub(r"^\d+\.\s", "", line)
                        list_items.append(f"<li>{item_text}</li>")
                if list_items:
                    p = f"<ol>{''.join(list_items)}</ol>"
            elif not p.startswith("<"):
                p = f"<p>{p}</p>"
            processed_paragraphs.append(p)
        content = "\n".join(processed_paragraphs)

        return f"<details>\n{summary}\n{content}\n</details>"

    # Match <details>...</details> blocks
    text = re.sub(r"<details>.*?</details>", render_details_block, text, flags=re.DOTALL)
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
            print(f"[DEBUG] Loading local content: {section['local_path']}")
            text = _read_local_content(section["local_path"])
        else:
            path = section.get("path")
            print(f"[DEBUG] Section '{section_id}' path: {path}")
            if not path:
                print(f"[DEBUG] WARNING: No 'path' key in section: {section}")
                raise Http404(f"No path configured for section {section_id}")
            text = _fetch_text(_raw_url(path))
        subsections = _parse_subsections(text)
    except Http404 as e:
        print(f"[DEBUG] Http404 caught: {e}")
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
        print(f"[DEBUG] RequestException caught: {e}")
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

        # Use allowed_special="all" to handle markdown content that may contain
        # sequences resembling special tokens (e.g., <|endoftext|>)
        tokens = _tiktoken_encoder.encode(text, allowed_special="all")
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
            course_summary += (
                "ARENA (Alignment Research Engineer Accelerator) is a comprehensive curriculum covering:\n\n"
            )
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


# =============================================================================
# PAPERS DOWNLOAD FEATURE
# =============================================================================

# Directory for local paper text files (for non-arXiv content like blog posts)
PAPERS_DIR = Path(__file__).parent / "papers"

# Mapping of section IDs to their associated papers
# Each paper is either:
#   - {"arxiv": "XXXX.XXXXX"} for arXiv papers (will be fetched as PDF)
#   - {"local": "filename.txt"} for local text files (blog posts, etc.)
SECTION_PAPERS = {
    "01_transformers": [  # 1.1 Transformer from Scratch
        {"arxiv": "1706.03762", "title": "Attention Is All You Need"},
        {"arxiv": "2005.14165", "title": "Language Models are Few-Shot Learners (GPT-3)"},
        {"arxiv": "2203.02155", "title": "Training language models to follow instructions (InstructGPT)"},
    ],
    "02_intro_mech_interp": [  # 1.2 Intro to Mech Interp
        {"arxiv": "2309.15046", "title": "A Mathematical Framework for Transformer Circuits"},
        {"arxiv": "2209.11895", "title": "In-context Learning and Induction Heads"},
    ],
    "11_probing": [  # 1.3.1 Probing for Deception
        {"arxiv": "2502.03407", "title": "Detecting Strategic Deception Using Linear Probes"},
    ],
    "12_function_vectors": [  # 1.3.2 Function Vectors & Model Steering
        {"arxiv": "2310.15213", "title": "Function Vectors in Large Language Models"},
    ],
    "13_saes": [  # 1.3.3 Interpretability with SAEs
        {"arxiv": "2209.10652", "title": "Toy Models of Superposition"},
        {"local": "monosemanticity_2023.txt", "title": "Towards Monosemanticity (2023)"},
        {"local": "scaling_monosemanticity_2024.txt", "title": "Scaling Monosemanticity (2024)"},
    ],
    "14_activation_oracles": [  # 1.3.4 Activation Oracles
        {
            "arxiv": "2512.15674",
            "title": "Activation Oracles: Training and Evaluating LLMs as General-Purpose Activation Explainers",
        },
    ],
    "21_ioi": [  # 1.4.1 Indirect Object Identification
        {"arxiv": "2211.00593", "title": "Interpretability in the Wild (IOI)"},
        {"arxiv": "2304.14997", "title": "Automated Circuit DisCovery (ACDC)"},
    ],
    "22_sae_circuits": [  # 1.4.2 SAE Circuits
        {"local": "monosemanticity_2023.txt", "title": "Towards Monosemanticity (2023)"},
        {"local": "scaling_monosemanticity_2024.txt", "title": "Scaling Monosemanticity (2024)"},
        {"local": "attribution_graphs_2025.txt", "title": "Circuit Tracing with Attribution Graphs"},
        {"arxiv": "2403.19647", "title": "Sparse Feature Circuits"},
    ],
    "31_brackets": [  # 1.5.1 Balanced Bracket Classifier
        {"arxiv": "2209.10652", "title": "Toy Models of Superposition"},
        {"arxiv": "2312.06550", "title": "Towards Monosemanticity (arXiv version)"},
    ],
    "32_grokking": [  # 1.5.2 Grokking & Modular Arithmetic
        {"local": "grokking_analysis.txt", "title": "A Mechanistic Interpretability Analysis of Grokking"},
    ],
    "33_othellogpt": [  # 1.5.3 OthelloGPT
        {"arxiv": "2309.00941", "title": "Emergent Linear Representations in World Models"},
        {
            "local": "othello_linear_representation.txt",
            "title": "Actually, Othello-GPT Has A Linear Emergent World Representation",
        },
    ],
    "34_superposition": [  # 1.5.4 Superposition & SAEs
        {"arxiv": "2209.10652", "title": "Toy Models of Superposition"},
        {"local": "monosemanticity_2023.txt", "title": "Towards Monosemanticity (2023)"},
    ],
    "41_emergent_misalignment": [  # 1.6.1 Emergent Misalignment
        {"arxiv": "2502.17424", "title": "Emergent Misalignment"},
        {"arxiv": "2506.11618", "title": "Convergent Linear Representations of Emergent Misalignment"},
        {"arxiv": "2506.11613", "title": "Model Organisms for Emergent Misalignment"},
    ],
    "42_science_misalignment": [  # 1.6.2 Science of Misalignment
        {"arxiv": "2412.14093", "title": "Alignment Faking in Large Language Models"},
        {"local": "shutdown_resistance_palisade.txt", "title": "Shutdown resistance in reasoning models"},
        {"local": "shutdown_resistance_followup.txt", "title": "Self-preservation or Instruction Ambiguity"},
    ],
    "43_reasoning_models": [  # 1.6.3 Thought Anchors
        {"arxiv": "2506.19143", "title": "Thought Anchors: Which LLM Reasoning Steps Matter?"},
    ],
    "44_persona_vectors": [  # 1.6.4 LLM Psychology & Persona Vectors
        {"arxiv": "2601.10387", "title": "The Assistant Axis"},
        {"arxiv": "2507.21509", "title": "Persona Vectors"},
    ],
}


def _arxiv_to_pdf_url(arxiv_id: str) -> str:
    """Convert arXiv ID to PDF download URL."""
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"


def _fetch_arxiv_pdf(arxiv_id: str) -> bytes:
    """Fetch PDF content from arXiv."""
    pdf_url = _arxiv_to_pdf_url(arxiv_id)
    response = requests.get(pdf_url, timeout=60)
    response.raise_for_status()
    return response.content


def _read_local_paper(filename: str) -> str:
    """Read a local paper text file."""
    filepath = PAPERS_DIR / filename
    if not filepath.exists():
        raise Http404(f"Paper file not found: {filename}")
    return filepath.read_text(encoding="utf-8")


@csrf_exempt
@require_POST
def download_papers_api(request):
    """
    API endpoint to download papers for selected sections.
    Returns a ZIP file containing PDFs (from arXiv) and text files (local).

    Accepts JSON body with:
    - section_ids: list of section IDs to get papers for
    """
    try:
        data = json.loads(request.body)
        section_ids = data.get("section_ids", [])

        if not section_ids:
            return JsonResponse({"error": "No sections provided"}, status=400)

        # Collect unique papers across all sections
        papers_to_fetch = {}  # Use dict to deduplicate by arxiv ID or filename

        for section_id in section_ids:
            papers = SECTION_PAPERS.get(section_id, [])
            for paper in papers:
                if "arxiv" in paper:
                    key = f"arxiv:{paper['arxiv']}"
                    papers_to_fetch[key] = paper
                elif "local" in paper:
                    key = f"local:{paper['local']}"
                    papers_to_fetch[key] = paper

        if not papers_to_fetch:
            return JsonResponse({"error": "No papers found for selected sections"}, status=404)

        # Create ZIP file in memory
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for key, paper in papers_to_fetch.items():
                title = paper.get("title", "Unknown")
                # Sanitize title for filename
                safe_title = re.sub(r'[<>:"/\\|?*]', "", title)[:50]

                try:
                    if "arxiv" in paper:
                        # Fetch PDF from arXiv
                        arxiv_id = paper["arxiv"]
                        pdf_content = _fetch_arxiv_pdf(arxiv_id)
                        filename = f"{safe_title} [{arxiv_id}].pdf"
                        zip_file.writestr(filename, pdf_content)
                    elif "local" in paper:
                        # Read local text file
                        local_filename = paper["local"]
                        text_content = _read_local_paper(local_filename)
                        filename = f"{safe_title}.txt"
                        zip_file.writestr(filename, text_content.encode("utf-8"))
                except Exception as e:
                    # Log error but continue with other papers
                    print(f"Error fetching paper {key}: {e}")
                    continue

        zip_buffer.seek(0)

        # Return ZIP file
        response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = 'attachment; filename="arena_papers.zip"'
        return response

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
