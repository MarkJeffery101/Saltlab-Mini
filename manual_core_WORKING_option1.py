# ============================================================
#  manual_core.py  (STABLE BUILD – hierarchy + noise filtering)
#  Compact Manual Intelligence Engine v2
# ============================================================

import os
import json
import math
import argparse
import csv
import re
from typing import List, Dict, Any, Optional, Tuple

from openai import OpenAI
client = OpenAI()

# -----------------------------------------
# CONFIG
# -----------------------------------------
MANUALS_DIR = "manuals"
DB_PATH = "db.json"
REPORTS_DIR = "reports"

EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL  = "gpt-4o-mini"

# -----------------------------------------
# NOISE / CLEANING
# -----------------------------------------

NOISE_LINE_RE = re.compile(
    r"^(procedures|global standard|document\s+no:|rev\.?\s*no:|date\s+issued:|"
    r"document\s+owner:|document\s+originator:|document\s+approver:|disclaimer:|"
    r"page:\s*\d+\s*of\s*\d+)\b",
    re.IGNORECASE,
)

# catches footer-like "Name   Name   Name" on one line (your Mike Paton / John Rossier case)
MULTI_NAME_LINE_RE = re.compile(
    r"^\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)(\s{2,}\1)+\s*$"
)

KNOWN_FOOTER_NAMES = {"mike paton", "john rossier"}

def is_noise_line(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return False

    if NOISE_LINE_RE.match(s):
        return True

    low = s.lower()
    if low in KNOWN_FOOTER_NAMES:
        return True

    # "Mike Paton   Mike Paton   John Rossier" or similar repeated-name footer lines
    # also catch lines that are mostly names separated by huge spaces
    if MULTI_NAME_LINE_RE.match(s):
        return True

    # if line contains only names + big spacing (very common PDF footer)
    if re.fullmatch(r"[A-Za-z\s]{6,}", s) and re.search(r"\s{6,}", s):
        # if most tokens look like name-ish words
        toks = [t for t in s.split() if t]
        if len(toks) >= 3 and sum(t[0].isupper() for t in toks) >= max(2, len(toks) // 2):
            return True

    return False


def clean_text_for_chunking(text: str) -> str:
    """
    Light cleanup BEFORE chunking:
    - removes obvious header/footer/noise lines
    - collapses huge blank runs (keeps max 2 blanks)
    """
    lines = (text or "").splitlines()
    out: List[str] = []
    blank_run = 0

    for line in lines:
        s = line.rstrip()

        if is_noise_line(s):
            continue

        if not s.strip():
            blank_run += 1
            if blank_run <= 2:
                out.append("")
            continue

        blank_run = 0
        out.append(s)

    return "\n".join(out).strip()


def strip_noise_lines(text: str) -> str:
    """
    Stronger cleanup used for deciding if a chunk is "real" content.
    Removes repeated headers/footers/names but keeps structure.
    """
    lines = (text or "").splitlines()
    kept: List[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            kept.append("")
            continue
        if is_noise_line(s):
            continue
        kept.append(ln.rstrip())

    out: List[str] = []
    blank = 0
    for ln in kept:
        if not ln.strip():
            blank += 1
            if blank <= 2:
                out.append("")
        else:
            blank = 0
            out.append(ln)

    return "\n".join(out).strip()


def is_toc_like_text(text: str) -> bool:
    """
    Detects TOC/index-ish chunks that you do NOT want embedded.
    """
    if not text:
        return False
    low = text.lower()
    if "table of contents" in low:
        return True

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False

    tocish = 0
    for ln in lines:
        if re.search(r"\.{5,}\s*\d+\s*$", ln):
            tocish += 1

    return (tocish / max(1, len(lines))) >= 0.25


def has_real_content(text: str, min_chars: int = 40) -> bool:
    t = strip_noise_lines(text)
    # remove bullets/symbols and squash whitespace
    t2 = re.sub(r"[\s•xX\-\*]+", " ", t).strip()
    return len(t2) >= min_chars


def drop_bad_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Removes chunks that are blank, TOC-like, or only noise after stripping.
    """
    out: List[Dict[str, Any]] = []
    for r in records:
        t = (r.get("text") or "").strip()
        if not t:
            continue
        if is_toc_like_text(t):
            continue
        if not has_real_content(t, min_chars=40):
            continue
        out.append(r)
    return out

# -----------------------------------------
# Ensure dirs exist
# -----------------------------------------
def ensure_dirs():
    os.makedirs(MANUALS_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)

# -----------------------------------------
# Load/save database
# -----------------------------------------
def load_db() -> Dict[str, Any]:
    if not os.path.isfile(DB_PATH):
        return {"chunks": []}
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db: Dict[str, Any]):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

# -----------------------------------------
# File → text
# -----------------------------------------
def read_manual_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

# -----------------------------------------
# Embeddings
# -----------------------------------------
def embed_texts(texts: List[str]) -> List[List[float]]:
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]

# -----------------------------------------
# Cosine similarity
# -----------------------------------------
def vnorm(v):
    return math.sqrt(sum(x*x for x in v))

def cosine(a, b):
    na, nb = vnorm(a), vnorm(b)
    if na == 0 or nb == 0:
        return 0.0
    return sum(x*y for x, y in zip(a, b)) / (na * nb)

# -----------------------------------------
# Heading + hierarchy chunking
# -----------------------------------------

def is_tableish(line: str) -> bool:
    t = (line or "").strip()
    if not t:
        return False

    # TOC dotted leaders are NOT tables
    if re.search(r"\.{5,}\s*\d+\s*$", t):
        return False

    # IMPORTANT: do NOT treat headings as tables just because of spacing
    if re.match(r"^\d+(\.\d+)*\s+[A-Za-z]", t):
        return False

    if "|" in t:
        return True

    # require multiple column gaps
    if len(re.findall(r"\S\s{3,}\S", t)) >= 2:
        return True

    # mostly numeric rows
    if len(re.findall(r"\b\d+(\.\d+)?\b", t)) >= 3 and not re.search(r"[A-Za-z]", t):
        return True

    return False


def is_heading_line(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return False
    if len(s) < 3 or len(s) > 140:
        return False

    # TOC dotted-leader lines are NOT headings
    if re.search(r"\.{5,}\s*\d+\s*$", s):
        return False

    # hierarchical numbered headings
    if re.match(r"^\d+(\.\d+)+\s+\S", s):
        return True

    # ALL CAPS-ish headings
    letters = [c for c in s if c.isalpha()]
    if letters:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio >= 0.75 and not s.endswith("."):
            return True

    # "1 INTRODUCTION" style
    m = re.match(r"^(\d+)\s+(.*)$", s)
    if m:
        rest = m.group(2).strip()
        if not rest:
            return False
        if re.search(r"\s{3,}", line):  # table/list row
            return False
        if rest.endswith(".") or re.search(r"[,:;]", rest):
            return False
        if any(c.isalpha() for c in rest):
            return True

    return False


def parse_heading(line: str) -> Optional[Tuple[str, str]]:
    """
    Returns (num, title) if line looks like a numbered heading.
    Key rule: title MUST contain at least one letter
    -> prevents "1 5" / "1 10" being treated as headings.
    """
    s = (line or "").strip()
    m = re.match(r"^(\d+(?:\.\d+)*)\s+(.*\S)\s*$", s)
    if not m:
        return None
    num = m.group(1)
    title = m.group(2).strip()
    if not re.search(r"[A-Za-z]", title):
        return None
    return num, title


def heading_level(num: str) -> int:
    return num.count(".") + 1


def heading_hierarchy_chunks(text: str, max_chars: int = 1400) -> List[Dict[str, Any]]:
    """
    Hierarchy-aware chunker producing:
      { "path": "...", "heading": "...", "text": "..." }

    Behaviour:
    - drops front matter until first real heading
    - prevents splitting immediately after a heading
    - IMPORTANT: when a chunk splits due to max_chars, the next chunk REPEATS the heading line
      so every chunk's TEXT is self-contained/readable.
    """
    lines = (text or "").splitlines()

    chunks: List[Dict[str, Any]] = []
    current_lines: List[str] = []
    current_len = 0

    stack: List[tuple[str, str]] = []
    current_heading = ""
    heading_line_raw = ""          # <-- store the raw heading line for repetition
    seen_heading = False

    last_was_heading = False
    body_lines_after_heading = 0
    MIN_BODY_LINES_AFTER_HEADING = 3

    def stack_path() -> str:
        return " > ".join(f"{n} {t}".strip() for n, t in stack)

    def flush():
        nonlocal current_lines, current_len, last_was_heading, body_lines_after_heading
        if current_lines:
            chunk_text = "\n".join(current_lines).strip()
            if chunk_text:
                chunks.append({
                    "path": stack_path(),
                    "heading": current_heading,
                    "text": chunk_text
                })
        current_lines = []
        current_len = 0
        last_was_heading = False
        body_lines_after_heading = 0

    for line in lines:
        stripped = (line or "").strip()
        if not stripped:
            continue

        # skip TOC markers
        if "table of contents" in stripped.lower():
            continue
        if re.search(r"\.{5,}\s*\d+\s*$", stripped):
            continue

        is_head = is_heading_line(line) and (not is_tableish(line))
        parsed = parse_heading(stripped) if is_head else None

        if parsed:
            num, title = parsed
            level = heading_level(num)

            # close previous section chunk
            if seen_heading and current_len > 0:
                flush()

            while len(stack) >= level:
                stack.pop()
            stack.append((num, title))

            current_heading = f"{num} {title}".strip()
            heading_line_raw = line          # <-- store raw heading line
            seen_heading = True

            # start new chunk with heading line
            current_lines = [heading_line_raw]
            current_len = len(heading_line_raw)
            last_was_heading = True
            body_lines_after_heading = 0
            continue

        # ignore all lines before first real heading
        if not seen_heading:
            continue

        projected = current_len + len(line) + 1

        if current_len > 0 and projected > max_chars:
            # don't split too soon after heading
            if not (last_was_heading and body_lines_after_heading < MIN_BODY_LINES_AFTER_HEADING):
                flush()
                # <-- NEW: after splitting, repeat heading line at top of the next chunk
                if heading_line_raw:
                    current_lines = [heading_line_raw]
                    current_len = len(heading_line_raw)
                    last_was_heading = True
                    body_lines_after_heading = 0
            # hard cap split
            elif projected > max_chars * 2:
                flush()
                if heading_line_raw:
                    current_lines = [heading_line_raw]
                    current_len = len(heading_line_raw)
                    last_was_heading = True
                    body_lines_after_heading = 0

        current_lines.append(line)
        current_len += len(line) + 1

        if last_was_heading:
            body_lines_after_heading += 1
            if body_lines_after_heading >= MIN_BODY_LINES_AFTER_HEADING:
                last_was_heading = False

    if seen_heading:
        flush()

    return chunks




def chunk_records(text: str, max_chars: int = 1400, use_hierarchy: bool = True) -> List[Dict[str, Any]]:
    if use_hierarchy:
        recs = heading_hierarchy_chunks(text, max_chars=max_chars)
        out: List[Dict[str, Any]] = []
        for r in recs:
            heading = (r.get("heading") or "").strip()
            num = ""
            lvl = 0
            p = parse_heading(heading)
            if p:
                num, _t = p
                lvl = heading_level(num)

            out.append({
                "text": r.get("text", ""),
                "heading": heading,
                "path": (r.get("path") or "").strip(),
                "heading_num": num,
                "level": lvl,
            })
        return out

    # (not used in your case, but kept safe)
    return [{"text": t} for t in (text or "").split("\n\n") if t.strip()]

# -----------------------------------------
# Delete / export / list / show
# -----------------------------------------
def delete_manual(manual_id: str, delete_file: bool = False) -> None:
    db = load_db()
    chunks = db.get("chunks", [])

    before = len(chunks)
    remaining = [c for c in chunks if c["manual_id"] != manual_id]
    removed = before - len(remaining)

    if removed == 0:
        print(f"No chunks found for manual_id='{manual_id}'. Nothing deleted.")
        return

    db["chunks"] = remaining
    save_db(db)

    print(f"Removed {removed} chunks for manual_id='{manual_id}'.")
    print(f"DB now has {len(remaining)} chunks total.")

    if delete_file:
        candidates = [
            os.path.join(MANUALS_DIR, manual_id + ".txt"),
            os.path.join(MANUALS_DIR, manual_id + ".md"),
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"Also deleted file: {path}")
                except OSError as e:
                    print(f"Could not delete file {path}: {e}")


def export_manual(manual_id: str, out_path: Optional[str] = None) -> None:
    db = load_db()
    chunks = [c for c in db.get("chunks", []) if c["manual_id"] == manual_id]
    if not chunks:
        print(f"No chunks found for manual_id='{manual_id}'. Nothing to export.")
        return

    if out_path is None:
        safe_name = "".join(ch if ch not in '<>:"/\\|?*' else "_" for ch in manual_id)
        out_path = f"{safe_name}_export.txt"

    text = "\n\n".join(c["text"] for c in chunks)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"Exported {len(chunks)} chunks for manual_id='{manual_id}'")
    print(f"Written to: {out_path}")


def list_manuals() -> None:
    db = load_db()
    chunks = db.get("chunks", [])
    if not chunks:
        print("Database is empty. Run 'ingest' first.")
        return

    counts: Dict[str, int] = {}
    for rec in chunks:
        counts[rec["manual_id"]] = counts.get(rec["manual_id"], 0) + 1

    print("\nManuals:\n")
    for mid, count in sorted(counts.items(), key=lambda x: x[0].lower()):
        print(f" • {mid}: {count} chunks")
    print(f"\nTotal: {len(chunks)}")


def show_chunk(chunk_id: str) -> None:
    db = load_db()
    chunks = db.get("chunks", [])
    for rec in chunks:
        if rec["id"] == chunk_id:
            print(f"\nmanual_id: {rec['manual_id']}")
            print(f"chunk_id : {rec['id']}")
            print(f"heading : {rec.get('heading','')}")
            print(f"path    : {rec.get('path','')}")
            print("\n---------- TEXT ----------\n")
            print(rec["text"])
            print("\n--------------------------\n")
            return
    print(f"Chunk with id '{chunk_id}' not found.")


# -----------------------------------------
# INGEST
# -----------------------------------------
def ingest(use_hierarchy: bool = True, max_chars: int = 1400):
    ensure_dirs()

    db = {"chunks": []}
    cid = 0

    files = [f for f in os.listdir(MANUALS_DIR) if f.lower().endswith((".txt", ".md"))]
    if not files:
        print("No .txt/.md files inside /manuals.")
        return

    print("FILES FOUND:")
    for f in files:
        print(" •", f)

    for fname in files:
        manual_id = os.path.splitext(fname)[0]
        path = os.path.join(MANUALS_DIR, fname)

        text = read_manual_file(path)
        text = clean_text_for_chunking(text)

        records = chunk_records(text, max_chars=max_chars, use_hierarchy=use_hierarchy)
        records = drop_bad_records(records)

        print(f"[{manual_id}] → {len(records)} chunks")

        batch_size = 16
        for i in range(0, len(records), batch_size):
            subrecs = records[i:i+batch_size]
            subtexts = [r["text"] for r in subrecs]
            embs = embed_texts(subtexts)

            for r, emb in zip(subrecs, embs):
                db["chunks"].append({
                    "id": f"C{cid}",
                    "manual_id": manual_id,
                    "text": r["text"],
                    "embedding": emb,
                    "heading": r.get("heading", ""),
                    "path": r.get("path", ""),
                    "heading_num": r.get("heading_num", ""),
                    "level": r.get("level", 0),
                })
                cid += 1

    save_db(db)
    print(f"\nIngestion complete. Total chunks: {len(db['chunks'])}")


# ============================================================
# ASK (Q&A retrieval)
# ============================================================
def ask(question: str, include: List[str] = None, top_k: int = 12):
    db = load_db()
    chunks = db.get("chunks", [])
    if not chunks:
        print("DB empty. Run: python manual_core.py ingest")
        return

    include = include or []
    q_emb = embed_texts([question])[0]

    scored = []
    for r in chunks:
        if include and not any(x.lower() in r["manual_id"].lower() for x in include):
            continue
        sim = cosine(q_emb, r["embedding"])
        scored.append((sim, r))

    scored.sort(reverse=True, key=lambda x: x[0])
    top = scored[:top_k]

    context = ""
    for i, (sim, r) in enumerate(top, 1):
        extras = []
        if r.get("heading"):
            extras.append(r["heading"])
        if r.get("path"):
            extras.append(r["path"])
        extra_txt = (" | " + " | ".join(extras)) if extras else ""
        context += (
            f"[Source {i} | {r['manual_id']} | {r['id']}{extra_txt}] (sim {sim:.3f})\n"
            f"{r['text']}\n\n"
        )

    system = (
        "You are a strict technical assistant. Use ONLY the given sources. "
        "If the answer is not explicitly in the text, say so."
    )
    user = f"QUESTION:\n{question}\n\nSOURCES:\n{context}\n\nAnswer strictly from sources."

    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=0.1
    )

    print("\n===== ANSWER =====\n")
    print(resp.choices[0].message.content)

    print("\n===== SOURCES USED =====\n")
    for i, (sim, r) in enumerate(top, 1):
        print(f"{i}. {r['manual_id']} | {r['id']} | sim={sim:.3f}")


def preview_manual(manual_id: str, start_index: int = 0, limit: int = 10) -> None:
    db = load_db()
    chunks = [c for c in db.get("chunks", []) if c["manual_id"] == manual_id]
    if not chunks:
        print(f"No chunks found for manual_id='{manual_id}'.")
        return

    total = len(chunks)
    start_index = max(0, start_index)
    end_index = min(start_index + limit, total)

    print(f"\nPreviewing manual_id='{manual_id}' chunks {start_index} to {end_index-1} of {total}:\n")
    for i in range(start_index, end_index):
        rec = chunks[i]
        txt = rec["text"].replace("\n", " ")
        preview = txt[:200] + ("..." if len(txt) > 200 else "")
        print(f"[{i}] chunk_id={rec['id']} heading={rec.get('heading','')}")
        print(f"     {preview}\n")


# ============================================================
# GAP ENGINE v2
# ============================================================
def classify_severity(coverage: str, similarity: float) -> str:
    if coverage == "Covered":
        return "None"
    if coverage == "Partially Covered":
        return "Medium"
    if coverage == "Not Covered":
        return "Critical" if similarity < 0.25 else "High"
    return "Unknown"


def analyze_gap(std_text: str, manual_context: str, standard_id: str, manual_id: str) -> str:
    system = (
        "You are performing a strict gap analysis between a STANDARD and an OPERATIONAL MANUAL. "
        "Classify as: Covered / Partially Covered / Not Covered. "
        "Be conservative. Do NOT assume coverage unless explicit."
    )
    user = (
        f"STANDARD ({standard_id}):\n{std_text}\n\n"
        f"MANUAL ({manual_id}):\n{manual_context}\n\n"
        "TASK:\n"
        "1. Summarise the requirement in one line.\n"
        "2. Classify coverage.\n"
        "3. Explain briefly.\n"
        "4. State which manual sources were used.\n"
    )

    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=0.1
    )
    return resp.choices[0].message.content


def gap(standard_id: str, manual_id: str, start_index=0, max_clauses=10,
        top_n=5, min_sim=0.40, out_csv=None, out_html=None):

    db = load_db()
    chunks = db.get("chunks", [])

    std_chunks = [c for c in chunks if c["manual_id"] == standard_id]
    man_chunks = [c for c in chunks if c["manual_id"] == manual_id]

    if not std_chunks:
        print("No standard chunks found.")
        return
    if not man_chunks:
        print("No manual chunks found.")
        return

    std_chunks = std_chunks[start_index:start_index + max_clauses]
    results = []

    for idx, std in enumerate(std_chunks, 1):
        scored = []
        for m in man_chunks:
            sim = cosine(std["embedding"], m["embedding"])
            scored.append((sim, m))
        scored.sort(reverse=True, key=lambda x: x[0])
        top = scored[:top_n]
        best_sim = top[0][0] if top else 0

        print("\n" + "="*72)
        print(f"STANDARD CHUNK {idx} | {std['id']} | best_sim={best_sim:.3f}")
        print("="*72)
        print(std["text"][:300] + "...\n")

        if best_sim < min_sim:
            coverage = "Not Covered"
            severity = classify_severity(coverage, best_sim)
            reason = f"No manual excerpts reached similarity ≥ {min_sim}. Best similarity = {best_sim:.3f}."
            results.append({
                "standard_chunk": std["id"],
                "standard_preview": std["text"][:200],
                "coverage": coverage,
                "severity": severity,
                "reason": reason,
                "manual_chunks": ""
            })
            print("AUTO CLASSIFIED: Not Covered")
            continue

        ctx = ""
        for i, (sim, m) in enumerate(top, 1):
            ctx += f"[{i} | {m['id']} | sim={sim:.3f}]\n{m['text']}\n\n"

        answer = analyze_gap(std["text"], ctx, standard_id, manual_id)
        coverage = (
            "Partially Covered" if "Partially" in answer
            else "Covered" if "Covered" in answer
            else "Not Covered"
        )
        severity = classify_severity(coverage, best_sim)

        results.append({
            "standard_chunk": std["id"],
            "standard_preview": std["text"][:200],
            "coverage": coverage,
            "severity": severity,
            "reason": answer,
            "manual_chunks": ";".join([m["id"] for _, m in top])
        })

        print(answer)

    if out_csv and results:
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=results[0].keys())
            w.writeheader()
            for r in results:
                w.writerow(r)
        print(f"\nCSV written → {out_csv}")

    if out_html and results:
        html = "<html><body><h1>Gap Report</h1>"
        for r in results:
            html += (
                f"<h2>{r['standard_chunk']} — {r['coverage']} (Severity: {r['severity']})</h2>"
                f"<p><b>Requirement:</b> {r['standard_preview']}</p>"
                f"<p><b>Analysis:</b> {r['reason']}</p><hr>"
            )
        html += "</body></html>"
        with open(out_html, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"HTML written → {out_html}")

# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Small, boring Q&A engine over local manuals.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ingest", help="Ingest all manuals/*.txt,*.md into the local DB.")
    sub.add_parser("list", help="List ingested manuals and chunk counts.")

    show_p = sub.add_parser("show", help="Show a specific chunk's text.")
    show_p.add_argument("chunk_id", type=str, help="Chunk id, e.g. C18")

    ask_p = sub.add_parser("ask", help="Ask a question over the ingested manuals.")
    ask_p.add_argument("question", type=str)
    ask_p.add_argument("--include", nargs="*", default=None)
    ask_p.add_argument("--top_k", type=int, default=12)

    prev_p = sub.add_parser("preview", help="Preview chunk text for a manual_id.")
    prev_p.add_argument("--manual-id", required=True)
    prev_p.add_argument("--start-index", type=int, default=0)
    prev_p.add_argument("--limit", type=int, default=10)

    gap_p = sub.add_parser("gap", help="Basic gap analysis: standard vs manual.")
    gap_p.add_argument("--standard-id", required=True)
    gap_p.add_argument("--manual-id", required=True)
    gap_p.add_argument("--max-clauses", type=int, default=5)
    gap_p.add_argument("--top-n", type=int, default=5)
    gap_p.add_argument("--start-index", type=int, default=0)
    gap_p.add_argument("--min-sim", type=float, default=0.35)
    gap_p.add_argument("--out-csv", type=str, default=None)
    gap_p.add_argument("--out-html", type=str, default=None)

    delete_p = sub.add_parser("delete", help="Delete a manual from the DB.")
    delete_p.add_argument("manual_id")
    delete_p.add_argument("--delete-file", action="store_true")

    export_p = sub.add_parser("export", help="Export a manual into a single text file.")
    export_p.add_argument("manual_id")
    export_p.add_argument("--out-path", type=str, default=None)

    args = parser.parse_args()

    if args.command == "ingest":
        ingest(use_hierarchy=True, max_chars=1400)
    elif args.command == "list":
        list_manuals()
    elif args.command == "show":
        show_chunk(args.chunk_id)
    elif args.command == "ask":
        ask(args.question, include=args.include, top_k=args.top_k)
    elif args.command == "preview":
        preview_manual(args.manual_id, start_index=args.start_index, limit=args.limit)
    elif args.command == "gap":
        gap(
            standard_id=args.standard_id,
            manual_id=args.manual_id,
            max_clauses=args.max_clauses,
            top_n=args.top_n,
            start_index=args.start_index,
            min_sim=args.min_sim,
            out_csv=args.out_csv,
            out_html=args.out_html,
        )
    elif args.command == "delete":
        delete_manual(args.manual_id, delete_file=args.delete_file)
    elif args.command == "export":
        export_manual(args.manual_id, out_path=args.out_path)

if __name__ == "__main__":
    main()


