/**
 * diff.js — the PR-preview "diff" view: this page side by side with the same
 * page on the live site, differences highlighted like a git diff.
 *
 * Ported from iliad-team/iliad-intensive (public/diff.js); the block/word diff
 * and the alignment pass are theirs, the fetching and the wiring are ours.
 *
 * Loaded ONLY inside a PR preview (base.html adds the script when the view
 * passes a `preview`), and inert unless the page shows a section article and
 * the banner's #diff-toggle checkbox exists.
 *
 * How it works
 *   1. Fetch this section twice from the section API: the preview's copy
 *      (<base path>/api/<chapter>/<section>/) and the live site's
 *      (/api/<chapter>/<section>/). Both are this origin, and the API returns
 *      rendered HTML per subsection, so there is nothing to scrape. If the
 *      current subsection does not exist on main, the checkbox disables itself
 *      and says so.
 *   2. Render both (KaTeX, copy buttons) and split them into LEAF BLOCKS —
 *      paragraphs, headings, list items, display equations, code blocks,
 *      tables — by descending through containers (div, details, ul...) until
 *      an element has no block children. A display equation is keyed by its
 *      TeX source, everything else by its normalised text.
 *   3. Sequence-diff the two block lists (common prefix/suffix stripped, then
 *      LCS). Unmatched blocks are removed (red, left) or added (green, right);
 *      a removed+added pair that share enough words is a MODIFIED pair, and
 *      gets a word-level diff inside (inline maths is one atomic token).
 *   4. Lay both articles out in two columns, then ALIGN them: for every matched
 *      pair, whichever side sits higher gets a spacer above it so the pair
 *      shares a row. Removed/added blocks therefore face a blank on the other
 *      side, exactly like GitHub's split view. Because the columns share the
 *      page's scroll, they stay in sync for free; "sync scroll" off gives each
 *      column its own scrollbar instead.
 *
 * Solutions (<details>) that contain a change are opened so the change shows.
 * Turning the view off re-renders the article from the preview's HTML.
 *
 * The site navigates client-side (chapter-nav.js swaps #content-area), so the
 * view follows the `arena:content-rendered` event rather than page loads.
 */
(function () {
  "use strict";

  var toggle = document.getElementById("diff-toggle");
  var syncBox = document.getElementById("diff-sync");
  var status = document.getElementById("diff-status");
  var controls = document.getElementById("diff-controls");
  var contentArea = document.getElementById("content-area");
  if (!toggle || !controls) return;
  if (!contentArea) { controls.hidden = true; return; }

  var root = document.documentElement;
  var KEY = "arena.diff";
  var SYNC_KEY = "arena.diffSync";
  var basePath = window.ARENA_BASE_PATH || "";

  var view = null;      // the two-column element, while the diff is showing
  var article = null;   // the live <article>, moved into the right column
  var prHtml = null;    // what to put back into it on teardown
  var fetches = {};     // api url -> promise of its JSON

  function store(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function load(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function say(msg) { if (status) status.textContent = msg || ""; }

  // ------------------------------------------------------------ fetch both sides
  // [chapterId, sectionId, subsectionId?] from the URL, preview prefix removed.
  function where() {
    var path = location.pathname;
    if (basePath && path.indexOf(basePath) === 0) path = path.slice(basePath.length);
    // Subsection ids are not always ASCII; the URL percent-encodes them.
    return path.split("/").filter(Boolean).map(function (part) {
      try { return decodeURIComponent(part); } catch (e) { return part; }
    });
  }
  function fetchSection(prefix, parts) {
    var url = prefix + "/api/" + parts[0] + "/" + parts[1] + "/";
    if (!fetches[url]) {
      fetches[url] = fetch(url, { credentials: "omit" }).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      });
      fetches[url].catch(function () { delete fetches[url]; });
    }
    return fetches[url];
  }
  function pick(data, subsectionId) {
    var subs = (data && data.subsections) || [];
    if (!subsectionId) return subs[0] || null;
    for (var i = 0; i < subs.length; i++) if (subs[i].id === subsectionId) return subs[i];
    return null;
  }
  function fill(el, html) {
    el.innerHTML = html;
    if (window.renderMath) window.renderMath(el);
    if (window.addCodeCopyButtons) window.addCodeCopyButtons(el);
  }

  // ------------------------------------------------------------ leaf blocks
  var BLOCK = /^(P|DIV|SECTION|UL|OL|LI|DETAILS|SUMMARY|H[1-6]|BLOCKQUOTE|TABLE|PRE|FIGURE|HEADER|FOOTER|ASIDE|NAV|HR)$/;

  function isAtomic(el) {
    return el.matches(".katex-display, table, pre, figure, svg, img, hr, .mermaid");
  }
  function hasBlockChildren(el) {
    for (var c = el.firstElementChild; c; c = c.nextElementSibling) {
      if (BLOCK.test(c.tagName) || c.classList.contains("katex-display")) return true;
    }
    return false;
  }
  // A container may hold inline runs beside its block children (an <li> whose
  // text is followed by a nested <ul>). Wrap each such run so it is a leaf too.
  function wrapInlineRuns(el) {
    var run = [];
    var flush = function () {
      // The copy button that right-sidebar.js hangs on a code block is chrome,
      // not content.
      var meaningful = run.some(function (n) {
        return n.nodeType === 1 ? !n.matches(".code-copy-button") : /\S/.test(n.nodeValue);
      });
      if (meaningful) {
        var span = document.createElement("span");
        span.className = "diff-inline-run";
        run[0].parentNode.insertBefore(span, run[0]);
        run.forEach(function (n) { span.appendChild(n); });
      }
      run = [];
    };
    var kids = Array.prototype.slice.call(el.childNodes);
    kids.forEach(function (n) {
      var block = n.nodeType === 1 && (BLOCK.test(n.tagName) || n.classList.contains("katex-display") || n.classList.contains("diff-spacer"));
      if (block) flush(); else run.push(n);
    });
    flush();
  }
  function leaves(el, out) {
    for (var c = el.firstElementChild; c; c = c.nextElementSibling) {
      if (c.classList.contains("diff-spacer")) continue;
      if (isAtomic(c) || !hasBlockChildren(c)) out.push(c);
      else { wrapInlineRuns(c); leaves(c, out); }
    }
    return out;
  }
  // KaTeX keeps the TeX source in its MathML annotation.
  function tex(el) {
    var ann = el.querySelector("annotation");
    return ann ? ann.textContent : el.textContent;
  }
  function blockKey(el) {
    if (el.classList.contains("katex-display")) return "M" + tex(el);
    return el.tagName + ":" + (el.textContent || "").replace(/\s+/g, " ").trim();
  }

  // ------------------------------------------------------------ sequence diff
  // ops: ["=", i, j] | ["-", i, -1] | ["+", -1, j], in order.
  function diffSeq(a, b) {
    var n = a.length, m = b.length, pre = 0, suf = 0, i, j;
    while (pre < n && pre < m && a[pre] === b[pre]) pre++;
    while (suf < n - pre && suf < m - pre && a[n - 1 - suf] === b[m - 1 - suf]) suf++;
    var ops = [];
    for (i = 0; i < pre; i++) ops.push(["=", i, i]);
    var N = n - pre - suf, M = m - pre - suf;
    if (N && M && N * M <= 6e6) {
      var W = M + 1, L = new Uint32Array((N + 1) * W);
      for (i = N - 1; i >= 0; i--) {
        for (j = M - 1; j >= 0; j--) {
          L[i * W + j] = a[pre + i] === b[pre + j]
            ? L[(i + 1) * W + j + 1] + 1
            : Math.max(L[(i + 1) * W + j], L[i * W + j + 1]);
        }
      }
      i = 0; j = 0;
      while (i < N && j < M) {
        if (a[pre + i] === b[pre + j]) { ops.push(["=", pre + i, pre + j]); i++; j++; }
        else if (L[(i + 1) * W + j] >= L[i * W + j + 1]) { ops.push(["-", pre + i, -1]); i++; }
        else { ops.push(["+", -1, pre + j]); j++; }
      }
      while (i < N) ops.push(["-", pre + i++, -1]);
      while (j < M) ops.push(["+", -1, pre + j++]);
    } else {
      for (i = 0; i < N; i++) ops.push(["-", pre + i, -1]);
      for (j = 0; j < M; j++) ops.push(["+", -1, pre + j]);
    }
    for (i = 0; i < suf; i++) ops.push(["=", n - suf + i, m - suf + i]);
    return ops;
  }

  // Within each run of removed/added blocks, pair up the ones that are the
  // same kind of element and share enough words: those are edits, not a
  // deletion plus an unrelated insertion. Returns ops with "~" pairs.
  function words(el) {
    var set = {};
    (el.textContent || "").toLowerCase().split(/[^a-z0-9\\]+/).forEach(function (w) { if (w) set[w] = 1; });
    return set;
  }
  function similarity(a, b) {
    var wa = words(a), wb = words(b), inter = 0, union = 0, k;
    for (k in wa) { union++; if (wb[k]) inter++; }
    for (k in wb) { if (!wa[k]) union++; }
    return union ? inter / union : 0;
  }
  function pairEdits(ops, A, B) {
    var out = [], run = [];
    var flush = function () {
      if (!run.length) return;
      var dels = run.filter(function (o) { return o[0] === "-"; });
      var ins = run.filter(function (o) { return o[0] === "+"; });
      var cands = [];
      dels.forEach(function (d) {
        ins.forEach(function (n) {
          var a = A[d[1]], b = B[n[2]];
          if (a.tagName !== b.tagName) return;
          var s = a.classList.contains("katex-display") ? 0.5 : similarity(a, b);
          if (s >= 0.3) cands.push([s, d, n]);
        });
      });
      cands.sort(function (x, y) { return y[0] - x[0]; });
      var usedD = new Set(), usedI = new Set(), pair = new Map();
      cands.forEach(function (c) {
        if (usedD.has(c[1]) || usedI.has(c[2])) return;
        usedD.add(c[1]); usedI.add(c[2]); pair.set(c[1], c[2]);
      });
      dels.forEach(function (d) {
        if (pair.has(d)) out.push(["~", d[1], pair.get(d)[2]]);
        else out.push(d);
      });
      ins.forEach(function (n) { if (!usedI.has(n)) out.push(n); });
      run = [];
    };
    ops.forEach(function (o) {
      if (o[0] === "=") { flush(); out.push(o); } else run.push(o);
    });
    flush();
    return out;
  }

  // ------------------------------------------------------------ word diff
  function tokens(el) {
    var out = [];
    (function walk(n) {
      if (n.nodeType === 3) {
        var re = /\s+|\S+/g, m, t = n.nodeValue;
        while ((m = re.exec(t))) {
          out.push({ node: n, start: m.index, end: m.index + m[0].length, key: /^\s+$/.test(m[0]) ? " " : m[0] });
        }
      } else if (n.nodeType === 1) {
        if (n.classList.contains("katex")) { out.push({ el: n, key: "M" + tex(n) }); return; }
        for (var c = n.firstChild; c; c = c.nextSibling) walk(c);
      }
    })(el);
    return out;
  }
  function applyMarks(toks, idxs, cls) {
    // Back to front: wrapping a range splits its text node, which would move
    // the offsets of every token after it in that node.
    for (var q = idxs.length - 1; q >= 0; q--) {
      var t = toks[idxs[q]];
      if (t.key === " ") continue;
      if (t.el) { t.el.classList.add(cls); continue; }
      var r = document.createRange();
      r.setStart(t.node, t.start); r.setEnd(t.node, t.end);
      var mark = document.createElement("mark");
      mark.className = cls;
      try { r.surroundContents(mark); } catch (e) {}
    }
  }
  function markWords(a, b) {
    var ta = tokens(a), tb = tokens(b);
    if (!ta.length || !tb.length || ta.length * tb.length > 4e6) return;
    var ops = diffSeq(ta.map(function (t) { return t.key; }), tb.map(function (t) { return t.key; }));
    var del = [], ins = [];
    ops.forEach(function (o) { if (o[0] === "-") del.push(o[1]); else if (o[0] === "+") ins.push(o[2]); });
    applyMarks(ta, del, "diff-del");
    applyMarks(tb, ins, "diff-ins");
  }

  // ------------------------------------------------------------ alignment
  function openDetails(el) {
    for (var d = el.closest("details"); d; d = d.parentElement && d.parentElement.closest("details")) d.open = true;
  }
  function mkSpacer() {
    var s = document.createElement("div");
    s.className = "diff-spacer";
    s.setAttribute("aria-hidden", "true");
    return s;
  }
  // Grow (or create) the spacer above `el`, hoisted out of any box `el` opens,
  // so the blank sits between boxes rather than inside one.
  function pad(el, colRoot, px) {
    var target = el;
    while (target.parentElement !== colRoot && !target.previousElementSibling) target = target.parentElement;
    var s = target.previousElementSibling;
    if (!(s && s.classList.contains("diff-spacer"))) {
      s = mkSpacer();
      target.parentNode.insertBefore(s, target);
      openDetails(s);
    }
    var h = Math.max(0, (parseFloat(s.style.height) || 0) + px);
    s.style.height = h + "px";
    // Hatch the blanks that stand in for a missing block; the few px that
    // only true-up margins around a spacer stay invisible.
    s.classList.toggle("diff-gap", h >= 20);
  }
  function visible(r) { return r.width > 0 || r.height > 0; }
  // One pass: measure every matched pair (no DOM writes), then pad whichever
  // side of each pair sits higher. Column shifts accumulate downwards, so the
  // predicted position of a pair is its measured top plus the padding already
  // added above it in its column.
  function settle(pairs, rootL, rootR) {
    var rects = pairs.map(function (p) { return [p[0].getBoundingClientRect(), p[1].getBoundingClientRect()]; });
    var accL = 0, accR = 0, moved = 0;
    pairs.forEach(function (p, k) {
      var ra = rects[k][0], rb = rects[k][1];
      if (!visible(ra) || !visible(rb)) return;
      var d = (ra.top + accL) - (rb.top + accR);
      if (Math.abs(d) < 0.5) return;
      if (d > 0) { pad(p[1], rootR, d); accR += d; } else { pad(p[0], rootL, -d); accL += -d; }
      moved++;
    });
    return moved;
  }

  // ------------------------------------------------------------ build / teardown
  function column(label, cls, content) {
    var col = document.createElement("div");
    col.className = "diff-col " + cls;
    var head = document.createElement("div");
    head.className = "diff-col-head";
    head.textContent = label;
    col.appendChild(head);
    col.appendChild(content);
    return col;
  }

  function build(baseHtml) {
    var base = document.createElement("article");
    base.className = "markdown-content";
    fill(base, baseHtml);
    // Its ids and #links must not collide with (or jump to) the PR column.
    Array.prototype.forEach.call(base.querySelectorAll("[id]"), function (e) { e.id = "base-" + e.id; });
    Array.prototype.forEach.call(base.querySelectorAll('a[href^="#"]'), function (a) {
      a.setAttribute("href", "#base-" + a.getAttribute("href").slice(1));
    });
    // Start the PR side from the same clean render as the base side.
    fill(article, prHtml);

    view = document.createElement("div");
    view.className = "diff-view";
    article.parentNode.insertBefore(view, article);
    view.appendChild(column("main (live site)", "diff-col-base", base));
    view.appendChild(column("this pull request", "diff-col-pr", article));
    root.classList.add("diff-open");

    var A = leaves(base, []), B = leaves(article, []);
    var ops = pairEdits(diffSeq(A.map(blockKey), B.map(blockKey)), A, B);
    var pairs = [], removed = 0, added = 0, modified = 0;
    ops.forEach(function (o) {
      if (o[0] === "=") { pairs.push([A[o[1]], B[o[2]]]); return; }
      if (o[0] === "-") { A[o[1]].classList.add("diff-removed"); openDetails(A[o[1]]); removed++; return; }
      if (o[0] === "+") { B[o[2]].classList.add("diff-added"); openDetails(B[o[2]]); added++; return; }
      var a = A[o[1]], b = B[o[2]];
      a.classList.add("diff-modified"); b.classList.add("diff-modified");
      openDetails(a); openDetails(b);
      if (!a.classList.contains("katex-display")) markWords(a, b);
      pairs.push([a, b]);
      modified++;
    });
    say(removed + added + modified
      ? "−" + removed + " +" + added + " ~" + modified + " blocks"
      : "no differences in this subsection");

    var built = view;
    var align = function () {
      if (view !== built) return;
      settle(pairs, base, article);
      settle(pairs, base, article); // margins that stopped collapsing around new spacers
    };
    (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(align);
    // Images and lazy layout can land later; one more pass a moment on.
    setTimeout(align, 1500);
  }

  // Put the article back where it was, rendered afresh. If chapter-nav has
  // already replaced #content-area's contents, the view is gone with them and
  // there is nothing to restore.
  function teardown() {
    if (view && view.parentNode) {
      fill(article, prHtml);
      view.parentNode.replaceChild(article, view);
    }
    view = null;
    root.classList.remove("diff-open");
    say("");
  }

  // ------------------------------------------------------------ controls
  function enable() {
    var parts = where();
    article = contentArea.querySelector("article.markdown-content");
    if (parts.length < 2 || !article) { say(""); return; }
    say("loading main…");
    toggle.disabled = true;
    Promise.all([fetchSection(basePath, parts), fetchSection("", parts)]).then(function (both) {
      toggle.disabled = false;
      // Navigated away, or switched off, while loading.
      if (!toggle.checked || where().join("/") !== parts.join("/")) return;
      if (!article.isConnected) return;
      var mine = pick(both[0], parts[2]), theirs = pick(both[1], parts[2]);
      if (!mine) { say("no diff: subsection not found"); return; }
      if (!theirs) { say("no diff: subsection is new on this PR"); return; }
      prHtml = mine.html;
      build(theirs.html);
    }).catch(function (err) {
      toggle.checked = false;
      toggle.disabled = false;
      say("no diff: " + err.message);
    });
  }

  toggle.addEventListener("change", function () {
    store(KEY, toggle.checked ? "1" : "0");
    if (toggle.checked) enable(); else teardown();
  });

  // Client-side navigation rendered a new subsection.
  document.addEventListener("arena:content-rendered", function () {
    teardown();
    if (toggle.checked) enable();
  });

  if (syncBox) {
    var applySync = function () {
      root.classList.toggle("diff-unsync", !syncBox.checked);
      store(SYNC_KEY, syncBox.checked ? "1" : "0");
    };
    if (load(SYNC_KEY) === "0") syncBox.checked = false;
    applySync();
    syncBox.addEventListener("change", applySync);
  }

  if (load(KEY) === "1") { toggle.checked = true; enable(); }
})();
