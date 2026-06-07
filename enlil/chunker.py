"""
Domain-aware document chunker for ENLIL.

Three strategies based on god role:
  - POSITIONAL  : head + domain window (with 500-char overlap) + tail
  - DISTRIBUTED : head + evenly spaced samples + tail  (Anu, Tiamat)
  - DATA_DENSE  : head + 3 sections with highest number/date/legal-ref density + tail (Nabu)

For docs <= CHUNK_THRESHOLD: returned as-is (all gods see the full document).
"""

import re

CHUNK_THRESHOLD = 20_000   # chars — below this, no chunking applied
HEAD_CHARS      = 3_000    # always included: document start
TAIL_CHARS      = 2_000    # always included: document end
DOMAIN_CHARS    = 9_000    # body budget per god
OVERLAP_CHARS   = 500      # overlap at window boundaries (positional strategy)
SAMPLE_SIZE     = 1_500    # chars per sample (distributed strategy)
DENSE_SECTION   = 2_500    # chars per dense section (Nabu strategy)

# Gods that use distributed sampling (need global document view)
_DISTRIBUTED_DOMAINS = {
    "meta", "evolution", "orchestration", "patterns", "strategy",  # Anu
    "creative", "vision", "design", "generate", "multimodal", "unconventional",  # Tiamat
}

# Gods that use data-density sampling (need affirmations/numbers/dates)
_DENSE_DOMAINS = {
    "logic", "proof", "reasoning", "deduction", "inference",  # Nabu
}

# Positional windows per domain (0.0 = start, 1.0 = end).
# Where in a typical document is this specialty most likely to appear.
_DOMAIN_WINDOWS: dict[str, tuple[float, float]] = {
    "context":       (0.00, 0.35),
    "alignment":     (0.00, 0.35),
    "review":        (0.00, 0.50),
    "communication": (0.00, 0.30),
    "sales":         (0.00, 0.30),
    "writing":       (0.00, 0.30),
    "presentation":  (0.00, 0.30),
    "technical":     (0.20, 0.65),
    "code":          (0.20, 0.65),
    "architecture":  (0.20, 0.65),
    "analysis":      (0.20, 0.70),
    "math":          (0.25, 0.70),
    "security":      (0.35, 0.80),
    "threat":        (0.35, 0.80),
    "vulnerability": (0.35, 0.80),
    "audit":         (0.35, 0.80),
    "defense":       (0.35, 0.80),
    "attack":        (0.30, 0.80),
    "exploit":       (0.30, 0.80),
    "red-team":      (0.30, 0.80),
    "adversarial":   (0.30, 0.80),
    "penetration":   (0.30, 0.80),
    "supreme":       (0.55, 1.00),
    "critical":      (0.55, 1.00),
    "judgment":      (0.60, 1.00),
    "irreversible":  (0.60, 1.00),
    "final":         (0.65, 1.00),
    "decision":      (0.55, 1.00),
}

_DEFAULT_WINDOW = (0.15, 0.85)

# Regex for data-dense sections: numbers, dates, amounts, legal references
_DENSE_RE = re.compile(
    r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*(?:€|euros?|%)|'  # amounts/percentages
    r'art(?:ículo)?\.?\s*\d+|'                                # legal articles
    r'cláusula\s+\d+|'                                        # contract clauses
    r'párrafo\s+\d+|'                                         # paragraphs
    r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|'                       # dates
    r'(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|'
    r'septiembre|octubre|noviembre|diciembre)\s+de\s+\d{4}|' # Spanish dates
    r'resolución\s+\d+|'                                      # resolutions
    r'sentencia\s+\d+',                                       # sentences
    re.IGNORECASE,
)


def _snap_forward(text: str, pos: int) -> int:
    """Snap position forward to nearest paragraph or sentence boundary."""
    nl = text.find("\n\n", pos)
    if nl != -1 and nl < pos + 300:
        return nl + 2
    nl = text.find("\n", pos)
    if nl != -1 and nl < pos + 150:
        return nl + 1
    return pos


def _snap_backward(text: str, pos: int) -> int:
    """Snap position backward to nearest paragraph or sentence boundary."""
    nl = text.rfind("\n\n", max(0, pos - 300), pos)
    if nl != -1:
        return nl + 2
    nl = text.rfind("\n", max(0, pos - 150), pos)
    if nl != -1:
        return nl + 1
    return pos


def _build_result(text: str, head_end: int, tail_start: int,
                  sections: list[tuple[int, int, str]]) -> str:
    """
    Assemble head + body sections + tail with ellipsis markers.
    sections: list of (abs_start, abs_end, content) sorted by abs_start.
    """
    parts = [text[:head_end]]
    prev_end = head_end

    for abs_start, abs_end, content in sections:
        gap = abs_start - prev_end
        if gap > 100:
            parts.append(f"\n\n[... {gap:,} caracteres omitidos ...]\n\n")
        parts.append(content)
        prev_end = abs_end

    gap = tail_start - prev_end
    if gap > 100:
        parts.append(f"\n\n[... {gap:,} caracteres omitidos ...]\n\n")

    parts.append(text[tail_start:])
    return "".join(parts)


def _positional_window(text: str, domains: list[str],
                       head_end: int, tail_start: int) -> str:
    """Head + domain window with overlap + tail."""
    doc_len = len(text)
    primary = domains[0] if domains else ""
    start_r, end_r = _DOMAIN_WINDOWS.get(primary, _DEFAULT_WINDOW)

    win_start = int(doc_len * start_r)
    win_end   = int(doc_len * end_r)

    # Apply overlap at boundaries (extend window outward by OVERLAP_CHARS)
    if win_start > head_end + OVERLAP_CHARS:
        win_start -= OVERLAP_CHARS
    if win_end < tail_start - OVERLAP_CHARS:
        win_end += OVERLAP_CHARS

    # Clamp to body
    win_start = max(win_start, head_end)
    win_end   = min(win_end, tail_start)

    if win_start >= win_end:
        return text[:head_end] + text[tail_start:]

    # Fit within DOMAIN_CHARS budget
    window_size = win_end - win_start
    if window_size <= DOMAIN_CHARS:
        body_start = _snap_forward(text, win_start)
        body_end   = _snap_backward(text, win_end)
    else:
        center     = (win_start + win_end) // 2
        half       = DOMAIN_CHARS // 2
        body_start = _snap_forward(text, max(win_start, center - half))
        body_end   = _snap_backward(text, min(win_end, body_start + DOMAIN_CHARS))

    return _build_result(text, head_end, tail_start,
                         [(body_start, body_end, text[body_start:body_end])])


def _distributed_sample(text: str, head_end: int, tail_start: int) -> str:
    """
    Head + evenly distributed samples from the body + tail.
    For Anu (patterns) and Tiamat (creative): needs a global pulse, not a local window.
    """
    body = text[head_end:tail_start]
    body_len = len(body)

    if body_len <= DOMAIN_CHARS:
        return text  # body fits — no sampling needed

    n_samples = max(2, DOMAIN_CHARS // SAMPLE_SIZE)
    sections = []

    for i in range(n_samples):
        center_ratio = (i + 0.5) / n_samples
        center = int(body_len * center_ratio)
        raw_start = max(0, center - SAMPLE_SIZE // 2)
        raw_end   = min(body_len, raw_start + SAMPLE_SIZE)

        abs_start = head_end + _snap_forward(text, head_end + raw_start) - head_end
        # re-snap using actual text positions
        s = _snap_forward(text, head_end + raw_start)
        e = _snap_backward(text, head_end + raw_end)
        if s < e:
            sections.append((s, e, text[s:e]))

    return _build_result(text, head_end, tail_start, sections)


def _dense_section_sample(text: str, head_end: int, tail_start: int) -> str:
    """
    Head + 3 sections with highest density of numbers/dates/legal refs + tail.
    For Nabu (logic/proof): needs the affirmations most likely to contain contradictions.
    """
    body = text[head_end:tail_start]
    body_len = len(body)

    if body_len <= DOMAIN_CHARS:
        return text

    n_sections = 3
    step = max(1, body_len // (n_sections * 8))

    scored: list[tuple[int, int]] = []  # (score, body_pos)
    for pos in range(0, body_len - DENSE_SECTION, step):
        chunk = body[pos:pos + DENSE_SECTION]
        score = len(_DENSE_RE.findall(chunk))
        scored.append((score, pos))

    scored.sort(reverse=True)

    # Select top-N non-overlapping sections
    selected_positions: list[int] = []
    for _, pos in scored:
        if not any(abs(pos - sel) < DENSE_SECTION for sel in selected_positions):
            selected_positions.append(pos)
            if len(selected_positions) >= n_sections:
                break

    selected_positions.sort()

    sections = []
    for pos in selected_positions:
        s = _snap_forward(text, head_end + pos)
        e = _snap_backward(text, head_end + pos + DENSE_SECTION)
        if s < e:
            sections.append((s, e, text[s:e]))

    if not sections:
        # Fallback: evenly spaced if no dense sections found
        return _distributed_sample(text, head_end, tail_start)

    return _build_result(text, head_end, tail_start, sections)


def chunk_for_god(text: str, domains: list[str]) -> str:
    """
    Returns a tailored view of the document for a god with the given domains.
    If text <= CHUNK_THRESHOLD, returns the full document unchanged.
    """
    if len(text) <= CHUNK_THRESHOLD:
        return text

    doc_len   = len(text)
    head_end  = _snap_forward(text, HEAD_CHARS)
    tail_start = _snap_backward(text, doc_len - TAIL_CHARS)

    if head_end >= tail_start:
        return text  # very short structured doc — return as-is

    primary = domains[0] if domains else ""

    if primary in _DISTRIBUTED_DOMAINS:
        return _distributed_sample(text, head_end, tail_start)

    if primary in _DENSE_DOMAINS:
        return _dense_section_sample(text, head_end, tail_start)

    return _positional_window(text, domains, head_end, tail_start)


def needs_chunking(text: str) -> bool:
    return len(text) > CHUNK_THRESHOLD


def document_stats(text: str) -> dict:
    return {
        "chars": len(text),
        "words": len(text.split()),
        "needs_chunking": needs_chunking(text),
        "estimated_pages": round(len(text) / 2500, 1),
    }
