#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL Compare with GUI (Tkinter) + CLI
- Pure standard library; works on Windows/Notepad++.
- Modes:
    * whitespace-only (optional flag): collapse whitespace and compare only text shape
    * exact-token compare (ignores case/whitespace/comments; respects tokens)
    * canonical compare (order-insensitive SELECT list, WHERE AND-terms, and (optionally) JOIN runs)
- GUI launches when no args.

Features:
  - Color-coded HTML report with improved CSS and a legend.
  - Global toggle to enable/disable join reordering (default: enabled).
  - Optional LEFT JOIN and FULL OUTER JOIN reordering (heuristics; opt-in).
  - Summarized differences in TXT/HTML reports and console/GUI.

CLI Examples:
  python sql_compare.py file1.sql file2.sql --mode both --report diff.html --report-format html
  python sql_compare.py --strings "select b,a from t" "SELECT a,b FROM t" --ignore-whitespace
  type queries.txt | python sql_compare.py --stdin --mode canonical --allow-full-outer-reorder --allow-left-reorder
"""

import argparse
import difflib
import os
import re
import sys
import itertools
from pathlib import Path

SQL_CLAUSE_TERMINATORS = ["WHERE", "GROUP BY", "HAVING", "ORDER BY", "LIMIT", "OFFSET", "QUALIFY", "WINDOW", "UNION", "INTERSECT", "EXCEPT"]
from collections import Counter
WHITESPACE_REGEX = re.compile(r'\s+')



# --- Optional GUI imports guarded ---

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    TK_AVAILABLE = True
except Exception:
    TK_AVAILABLE = False
CLAUSE_TERMINATORS = (
    "WHERE", "GROUP BY", "HAVING", "ORDER BY", "LIMIT", "OFFSET",
    "QUALIFY", "WINDOW", "UNION", "INTERSECT", "EXCEPT"
)

# Normalization & Utilities
# =============================

MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

def safe_read_file(path_str: str) -> str:
    """Read a file safely, enforcing a size limit to prevent DoS."""
    p = Path(path_str)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path_str}")

    size = p.stat().st_size
    if size > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"File too large: {path_str} ({size / (1024*1024):.2f} MB). Limit is {MAX_FILE_SIZE_MB} MB.")

    return p.read_text(encoding="utf-8", errors="ignore")

def strip_sql_comments(s: str) -> str:
    """Remove -- line comments and /* ... */ block comments (non-nested)."""
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    s = re.sub(r"--[^\n\r]*", "", s)
    return s


def collapse_whitespace(s: str) -> str:
    """Collapse runs of whitespace to a single space and strip."""
    return WHITESPACE_REGEX.sub(" ", s).strip()


def uppercase_outside_quotes(s: str) -> str:
    """
    Uppercase characters outside of quoted regions:
      single quotes '...'; double quotes "..."; [brackets]; `backticks`
    """
    out = []
    i = 0
    mode = None  # 'single', 'double', 'bracket', 'backtick'
    while i < len(s):
        ch = s[i]
        if mode is None:
            if ch == "'":
                mode = 'single'
                out.append(ch)
            elif ch == '"':
                mode = 'double'
                out.append(ch)
            elif ch == '[':
                mode = 'bracket'
                out.append(ch)
            elif ch == '`':
                mode = 'backtick'
                out.append(ch)
            else:
                out.append(ch.upper())
        elif mode == 'single':
            out.append(ch)
            if ch == "'":
                if i + 1 < len(s) and s[i + 1] == "'":
                    out.append(s[i + 1]); i += 1
                else:
                    mode = None
        elif mode == 'double':
            out.append(ch)
            if ch == '"':
                if i + 1 < len(s) and s[i + 1] == '"':
                    out.append(s[i + 1]); i += 1
                else:
                    mode = None
        elif mode == 'bracket':
            out.append(ch)
            if ch == ']':
                mode = None
        elif mode == 'backtick':
            out.append(ch)
            if ch == '`':
                mode = None
        i += 1
    return "".join(out)


def remove_trailing_semicolon(s: str) -> str:
    s = s.strip()
    return s[:-1] if s.endswith(";") else s


def remove_outer_parentheses(s: str) -> str:
    """Remove one or more layers of outer wrapping parentheses if they enclose the full statement."""
    def is_wrapped(text: str) -> bool:
        if not (text.startswith("(") and text.endswith(")")):
            return False
        level = 0; mode = None; i = 0
        while i < len(text):
            ch = text[i]
            if mode is None:
                if ch == "'": mode = 'single'
                elif ch == '"': mode = 'double'
                elif ch == '[': mode = 'bracket'
                elif ch == '`': mode = 'backtick'
                elif ch == '(':
                    level += 1
                elif ch == ')':
                    level -= 1
                    if level == 0 and i != len(text) - 1:
                        return False
            elif mode == 'single':
                if ch == "'":
                    if i + 1 < len(text) and text[i + 1] == "'":
                        i += 1
                    else:
                        mode = None
            elif mode == 'double':
                if ch == '"':
                    if i + 1 < len(text) and text[i + 1] == '"':
                        i += 1
                    else:
                        mode = None
            elif mode == 'bracket':
                if ch == ']': mode = None
            elif mode == 'backtick':
                if ch == '`': mode = None
            i += 1
        return level == 0
    changed = True
    while changed:
        changed = False
        s_stripped = s.strip()
        if s_stripped.startswith("(") and s_stripped.endswith(")") and is_wrapped(s_stripped):
            s = s_stripped[1:-1].strip()
            changed = True
    return s


TOKEN_REGEX = re.compile(
    r"""
    (?:'(?:(?:''|[^'])*?)')            # single-quoted string
  | (?:(?:(?:\bE)?")(?:(?:""|[^"])*?)")  # double-quoted string (allow E"..." too)
  | (?:\[(?:[^\]]*?)\])                # [bracketed] identifier
  | (?:`(?:[^`]*?)`)                   # `backticked` identifier
  | (?:[A-Z_][A-Z0-9_\$]*\b)           # identifiers/keywords (after uppercasing)
  | (?:[0-9]+\.[0-9]+|[0-9]+)          # numbers
  | (?:<=|>=|<>|!=|:=|->|::)           # multi-char operators
  | (?:[(),=*\/\+\-<>\.%])             # single-char tokens
  | (?:\.)                             # dot
  | (?:\s+)                            # whitespace (filtered out)
    """,
    re.VERBOSE | re.IGNORECASE,
)

def tokenize(sql: str):
    return [m.group(0) for m in TOKEN_REGEX.finditer(sql) if not m.group(0).isspace()]


def split_top_level(s: str, sep: str) -> list:
    """Split by sep at top-level (not inside quotes/parentheses/brackets/backticks)."""
    parts, buf = [], []
    level = 0; mode = None; i = 0
    while i < len(s):
        ch = s[i]
        if mode is None:
            if ch == "'": mode = 'single'
            elif ch == '"': mode = 'double'
            elif ch == '[': mode = 'bracket'
            elif ch == '`': mode = 'backtick'
            elif ch == '(':
                level += 1
            elif ch == ')':
                level = max(0, level - 1)
            if level == 0 and s.startswith(sep, i):
                parts.append("".join(buf).strip()); buf = []; i += len(sep); continue
        else:
            if mode == 'single' and ch == "'":
                if i + 1 < len(s) and s[i + 1] == "'": buf.append(ch); i += 1
                else: mode = None
            elif mode == 'double' and ch == '"':
                if i + 1 < len(s) and s[i + 1] == '"': buf.append(ch); i += 1
                else: mode = None
            elif mode == 'bracket' and ch == ']': mode = None
            elif mode == 'backtick' and ch == '`': mode = None
        buf.append(ch); i += 1
    if buf: parts.append("".join(buf).strip())
    return [p for p in parts if p != ""]


def top_level_find_kw(sql: str, kw: str, start: int = 0):
    """Find top-level occurrence of keyword kw (word boundary) starting at start."""
    kw = kw.upper()
    i = start; mode = None; level = 0
    while i < len(sql):
        ch = sql[i]
        if mode is None:
            if ch == "'": mode = 'single'
            elif ch == '"': mode = 'double'
            elif ch == '[': mode = 'bracket'
            elif ch == '`': mode = 'backtick'
            elif ch == '(':
                level += 1
            elif ch == ')':
                level = max(0, level - 1)
            if level == 0:
                m = re.match(rf"\b{re.escape(kw)}\b", sql[i:])
                if m: return i
        else:
            if mode == 'single' and ch == "'":
                if i + 1 < len(sql) and sql[i + 1] == "'": i += 1
                else: mode = None
            elif mode == 'double' and ch == '"':
                if i + 1 < len(sql) and sql[i + 1] == '"': i += 1
                else: mode = None
            elif mode == 'bracket' and ch == ']': mode = None
            elif mode == 'backtick' and ch == '`': mode = None
        i += 1
    return -1


def clause_end_index(sql: str, start: int) -> int:
    """
    Find end index for a clause (FROM or WHERE) to the next top-level major keyword.
    """
    terms = CLAUSE_TERMINATORS
    ends = []
    for term in SQL_CLAUSE_TERMINATORS:
        idx = top_level_find_kw(sql, term, start)
        if idx != -1: ends.append(idx)
    return min(ends) if ends else len(sql)


# =============================
# Canonicalization helpers
# =============================

def normalize_sql(sql: str) -> str:
    """Full normalization pipeline."""
    sql = sql.strip()
    sql = strip_sql_comments(sql)
    sql = collapse_whitespace(sql)
    sql = remove_trailing_semicolon(sql)
    sql = remove_outer_parentheses(sql)
    sql = uppercase_outside_quotes(sql)
    sql = collapse_whitespace(sql)
    return sql


def ws_only_normalize(sql: str) -> str:
    """
    Whitespace-only normalization:
    - collapse whitespace
    - trim
    - remove trailing semicolon
    Does NOT remove comments or change case.
    """
    return remove_trailing_semicolon(collapse_whitespace(sql))


def canonicalize_select_list(sql: str) -> str:
    s = collapse_whitespace(sql)
    sel_i = top_level_find_kw(s, "SELECT", 0)
    if sel_i == -1: return s
    from_i = top_level_find_kw(s, "FROM", sel_i + 6)
    if from_i == -1: return s
    sel_list = s[sel_i + 6:from_i].strip()
    items = split_top_level(sel_list, ",")
    if len(items) > 1:
        items_sorted = sorted([collapse_whitespace(it) for it in items], key=lambda z: z.upper())
        s = s[:sel_i + 6] + " " + ", ".join(items_sorted) + " " + s[from_i:]
    return collapse_whitespace(s)


def canonicalize_where_and(sql: str) -> str:
    s = collapse_whitespace(sql)
    where_i = top_level_find_kw(s, "WHERE", 0)
    if where_i == -1: return s
    end_i = clause_end_index(s, where_i + 5)
    body = s[where_i + 5:end_i].strip()
    terms = split_top_level(body, " AND ")
    if len(terms) > 1:
        terms_sorted = sorted([collapse_whitespace(t) for t in terms], key=lambda z: z.upper())
        new_body = " AND ".join(terms_sorted)
        s = s[:where_i + 5] + " " + new_body + " " + s[end_i:]
    return collapse_whitespace(s)


def _parse_from_clause_body(body: str):
    """
    Parse FROM body into base and join segments.
    Returns: (base_text, segments)
    segment = dict(type='INNER'|'LEFT'|'RIGHT'|'FULL'|'CROSS'|'NATURAL'|...,
                   table='...',
                   cond_kw='ON'|'USING'|None,
                   cond='...' or '')
    Heuristic, top-level only.
    """
    i = 0; n = len(body)
    mode = None; level = 0
    tokens = []
    buf = []
    def flush_buf():
        nonlocal buf
        if buf:
            tokens.append(("TEXT", collapse_whitespace("".join(buf)).strip()))
            buf = []

    while i < n:
        ch = body[i]
        if mode is None:
            if ch == "'": mode = 'single'
            elif ch == '"': mode = 'double'
            elif ch == '[': mode = 'bracket'
            elif ch == '`': mode = 'backtick'
            elif ch == '(':
                level += 1
            elif ch == ')':
                level = max(0, level - 1)
            if level == 0:
                m = re.match(r"\b((?:NATURAL\s+)?(?:LEFT|RIGHT|FULL|INNER|CROSS)?(?:\s+OUTER)?\s*JOIN)\b", body[i:], flags=re.I)
                if m:
                    flush_buf()
                    tokens.append(("JOINKW", collapse_whitespace(m.group(1)).upper()))
                    i += m.end()
                    continue
                m2 = re.match(r"\b(ON|USING)\b", body[i:], flags=re.I)
                if m2:
                    flush_buf()
                    tokens.append(("CONDKW", m2.group(1).upper()))
                    i += m2.end()
                    continue
        else:
            if mode == 'single' and ch == "'":
                if i + 1 < n and body[i + 1] == "'": buf.append(ch); i += 1
                else: mode = None
            elif mode == 'double' and ch == '"':
                if i + 1 < n and body[i + 1] == '"': buf.append(ch); i += 1
                else: mode = None
            elif mode == 'bracket' and ch == ']': mode = None
            elif mode == 'backtick' and ch == '`': mode = None
        buf.append(ch); i += 1
    flush_buf()

    base = ""
    segments = []
    idx = 0
    while idx < len(tokens) and tokens[idx][0] != "JOINKW":
        kind, text = tokens[idx]
        if kind == "TEXT":
            base = (base + " " + text).strip()
        idx += 1

    while idx < len(tokens):
        if tokens[idx][0] != "JOINKW":
            idx += 1; continue
        join_kw = tokens[idx][1]
        idx += 1

        table_text = ""
        cond_kw = None
        cond_text = ""

        while idx < len(tokens) and tokens[idx][0] not in ("CONDKW", "JOINKW"):
            k, t = tokens[idx]
            if k == "TEXT":
                table_text = (table_text + " " + t).strip()
            idx += 1

        if idx < len(tokens) and tokens[idx][0] == "CONDKW":
            cond_kw = tokens[idx][1]
            idx += 1
            while idx < len(tokens) and tokens[idx][0] != "JOINKW":
                k, t = tokens[idx]
                if k == "TEXT":
                    cond_text = (cond_text + " " + t).strip()
                idx += 1

        seg_type = join_kw.replace(" OUTER", "")
        seg_type = seg_type.upper()
        if seg_type.endswith(" JOIN"):
            seg_type = seg_type[:-5]
        elif seg_type == "JOIN":
            seg_type = ""
        seg_type = seg_type.strip()
        if seg_type == "":
            seg_type = "INNER"
            seg_type = "INNER"
        segments.append({
            "type": seg_type,
            "table": collapse_whitespace(table_text),
            "cond_kw": cond_kw,
            "cond": collapse_whitespace(cond_text),
        })
    base = collapse_whitespace(base)
    return base, segments


def _rebuild_from_body(base: str, segments: list) -> str:
    """Rebuild FROM body from base and segments (already normalized)."""
    parts = [base] if base else []
    for seg in segments:
        join_kw = "JOIN" if seg["type"] == "INNER" else (seg["type"] + " JOIN")
        piece = f"{join_kw} {seg['table']}"
        if seg["cond_kw"] and seg["cond"]:
            piece += f" {seg['cond_kw']} {seg['cond']}"
        parts.append(piece)
    return " ".join(parts)


def canonicalize_joins(sql: str, allow_full_outer: bool = False, allow_left: bool = False) -> str:
    """
    Canonicalize top-level FROM JOIN chains by sorting contiguous runs of:
      - INNER/CROSS/NATURAL joins (always when join reordering is enabled)
      - FULL joins (only when allow_full_outer=True)
      - LEFT joins (only when allow_left=True)
    RIGHT joins are preserved (not commutative). FULL/LEFT also preserved unless explicitly allowed.
    """
    s = collapse_whitespace(sql)
    from_i = top_level_find_kw(s, "FROM", 0)
    if from_i == -1:
        return s
    end_i = clause_end_index(s, from_i + 4)
    body = s[from_i + 4:end_i].strip()
    if not body:
        return s

    base, segments = _parse_from_clause_body(body)
    if not segments:
        return s

    def is_reorderable(t: str) -> bool:
        tt = t.upper()
        if tt in ("INNER", "CROSS", "NATURAL"):
            return True
        if allow_full_outer and tt == "FULL":
            return True
        if allow_left and tt == "LEFT":
            return True
        return False

    new_segments = []
    for is_reo, group in itertools.groupby(segments, key=lambda seg: is_reorderable(seg["type"])):
        group_list = list(group)
        if is_reo:
            group_list.sort(key=lambda z: (z["type"], z["table"].upper(), z.get("cond_kw") or "", z.get("cond") or ""))
            new_segments.extend(group_list)
        else:
            new_segments.extend(group_list)

    rebuilt = _rebuild_from_body(base, new_segments)
    s2 = s[:from_i + 4] + " " + rebuilt + " " + s[end_i:]
    return collapse_whitespace(s2)


def canonicalize_common(sql: str, *, enable_join_reorder: bool = True, allow_full_outer: bool = False, allow_left: bool = False) -> str:
    """Apply canonicalizations: SELECT list, WHERE AND-terms, and (optionally) JOIN reordering."""
    s = collapse_whitespace(sql)
    s = canonicalize_select_list(s)
    s = canonicalize_where_and(s)
    if enable_join_reorder:
        s = canonicalize_joins(s, allow_full_outer=allow_full_outer, allow_left=allow_left)
    return collapse_whitespace(s)


# =============================
# Difference analysis (summary)
# =============================

def _select_items(sql: str):
    s = collapse_whitespace(sql)
    si = top_level_find_kw(s, "SELECT", 0)
    if si == -1: return []
    fi = top_level_find_kw(s, "FROM", si + 6)
    if fi == -1: return []
    lst = s[si + 6:fi].strip()
    items = [collapse_whitespace(x).upper() for x in split_top_level(lst, ",")]
    return items


def _where_and_terms(sql: str):
    s = collapse_whitespace(sql)
    wi = top_level_find_kw(s, "WHERE", 0)
    if wi == -1: return []
    end = clause_end_index(s, wi + 5)
    body = s[wi + 5:end].strip()
    terms = [collapse_whitespace(x).upper() for x in split_top_level(body, " AND ")]
    return terms


def _join_reorderable_segments(sql: str, enable_join_reorder: bool, allow_full_outer: bool, allow_left: bool):
    if not enable_join_reorder:
        return []
    s = collapse_whitespace(sql)
    fi = top_level_find_kw(s, "FROM", 0)
    if fi == -1: return []
    end = clause_end_index(s, fi + 4)
    body = s[fi + 4:end].strip()
    base, segs = _parse_from_clause_body(body)
    if not segs: return []
    def is_reo(t: str) -> bool:
        tt = t.upper()
        return (tt in ("INNER", "CROSS", "NATURAL")
                or (allow_full_outer and tt == "FULL")
                or (allow_left and tt == "LEFT"))
    reprs = []
    for seg in segs:
        if is_reo(seg["type"]):
            reprs.append((seg["type"].upper(), seg["table"].upper(), (seg.get("cond_kw") or "").upper(), (seg.get("cond") or "").upper()))
    return reprs


def build_difference_summary(norm_a: str, norm_b: str, can_a: str, can_b: str,
                             tokens_a: list, tokens_b: list,
                             *, enable_join_reorder: bool, allow_full_outer: bool, allow_left: bool):
    summary = []

    # SELECT analysis
    sel_a = _select_items(norm_a); sel_b = _select_items(norm_b)
    if sel_a or sel_b:
        ca, cb = Counter(sel_a), Counter(sel_b)
        if ca != cb:
            missing = list((ca - cb).elements())
            added   = list((cb - ca).elements())
            if missing:
                summary.append(f"SELECT list differs: items only in SQL1: {len(missing)}")
            if added:
                summary.append(f"SELECT list differs: items only in SQL2: {len(added)}")
        elif sel_a != sel_b:
            summary.append("SELECT list order differs (same items, different order).")

    # WHERE AND analysis
    and_a = _where_and_terms(norm_a); and_b = _where_and_terms(norm_b)
    ca, cb = Counter(and_a), Counter(and_b)
    if ca != cb:
        missing = list((ca - cb).elements())
        added   = list((cb - ca).elements())
        if missing:
            summary.append(f"WHERE AND terms differ: terms only in SQL1: {len(missing)}")
        if added:
            summary.append(f"WHERE AND terms differ: terms only in SQL2: {len(added)}")
    elif and_a != and_b:
        summary.append("WHERE AND term order differs (same terms, different order).")

    # JOIN analysis (only when reordering is enabled)
    if enable_join_reorder:
        reo_a = _join_reorderable_segments(norm_a, enable_join_reorder, allow_full_outer, allow_left)
        reo_b = _join_reorderable_segments(norm_b, enable_join_reorder, allow_full_outer, allow_left)
        if reo_a or reo_b:
            ca, cb = Counter(reo_a), Counter(reo_b)
            if ca != cb:
                diff_a = sum((ca - cb).values())
                diff_b = sum((cb - ca).values())
                if diff_a:
                    summary.append(f"Reorderable JOIN components differ: {diff_a} only in SQL1.")
                if diff_b:
                    summary.append(f"Reorderable JOIN components differ: {diff_b} only in SQL2.")
            elif reo_a != reo_b:
                summary.append("Reorderable JOIN segment order differs (same components, different order).")
    else:
        summary.append("Join reordering is disabled; join order is considered significant in comparisons.")

    # Token change counts
    sm = difflib.SequenceMatcher(a=tokens_a, b=tokens_b, autojunk=False)
    ins = del_ = rep = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'insert':   ins += (j2 - j1)
        elif tag == 'delete': del_ += (i2 - i1)
        elif tag == 'replace': rep += max(i2 - i1, j2 - j1)
    if ins or del_ or rep:
        summary.append(f"Token-level changes: +{ins} inserts, -{del_} deletes, ~{rep} replaces.")

    if not summary:
        summary.append("No structural differences detected beyond normalization.")
    return summary


# =============================
# Comparison
# =============================

def compare_sql(a: str, b: str,
                *, ignore_ws: bool = False,
                enable_join_reorder: bool = True,
                allow_full_outer: bool = False,
                allow_left: bool = False):
    """
    Return a result dict with:
      - ws_equal, ws_norm forms and diff
      - exact_equal (token-based on normalized)
      - canonical_equal (with SELECT/WHERE/JOIN canonicalization per flags)
      - summary (list of bullet strings)
    """
    ws_a = ws_only_normalize(a)
    ws_b = ws_only_normalize(b)
    ws_equal = (ws_a == ws_b)
    ws_diff = "\n".join(difflib.unified_diff(
        ws_a.splitlines(), ws_b.splitlines(),
        fromfile="sql1(ws)", tofile="sql2(ws)", lineterm=""
    ))

    norm_a = normalize_sql(a)
    norm_b = normalize_sql(b)
    tokens_a = tokenize(norm_a)
    tokens_b = tokenize(norm_b)
    exact_equal = (tokens_a == tokens_b)
    diff_norm = "\n".join(difflib.unified_diff(
        norm_a.splitlines(), norm_b.splitlines(),
        fromfile="sql1(norm)", tofile="sql2(norm)", lineterm=""
    ))

    can_a = canonicalize_common(norm_a, enable_join_reorder=enable_join_reorder,
                                allow_full_outer=allow_full_outer, allow_left=allow_left)
    can_b = canonicalize_common(norm_b, enable_join_reorder=enable_join_reorder,
                                allow_full_outer=allow_full_outer, allow_left=allow_left)
    canonical_equal = (can_a == can_b)
    diff_can = "\n".join(difflib.unified_diff(
        can_a.splitlines(), can_b.splitlines(),
        fromfile="sql1(canon)", tofile="sql2(canon)", lineterm=""
    ))

    summary = build_difference_summary(norm_a, norm_b, can_a, can_b, tokens_a, tokens_b,
                                       enable_join_reorder=enable_join_reorder,
                                       allow_full_outer=allow_full_outer,
                                       allow_left=allow_left)

    return {
        "ws_a": ws_a, "ws_b": ws_b, "ws_equal": ws_equal, "diff_ws": ws_diff,
        "norm_a": norm_a, "norm_b": norm_b, "tokens_a": tokens_a, "tokens_b": tokens_b,
        "exact_equal": exact_equal, "diff_norm": diff_norm,
        "can_a": can_a, "can_b": can_b, "canonical_equal": canonical_equal, "diff_can": diff_can,
        "summary": summary,
    }


# =============================
# CLI
# =============================

def parse_args(argv):
    p = argparse.ArgumentParser(description="Compare two SQL statements with Exact/Canonical modes and GUI.")
    p.add_argument("files", nargs="*", help="Two SQL files to compare")
    p.add_argument("--strings", nargs=2, metavar=("SQL1", "SQL2"), help="Provide two SQL strings inline")
    p.add_argument("--stdin", action="store_true", help="Read two SQL statements from stdin separated by a line with ---")
    p.add_argument("--mode", choices=["exact", "canonical", "both"], default="both", help="Comparison mode (default: both)")
    p.add_argument("--ignore-whitespace", action="store_true", help="Consider queries equal if they differ only by whitespace")

    # Global join reordering toggle (default ON) + fine-grained flags
    jg = p.add_mutually_exclusive_group()
    jg.add_argument("--join-reorder", dest="join_reorder", action="store_true", help="Enable join reordering (default)")
    jg.add_argument("--no-join-reorder", dest="join_reorder", action="store_false", help="Disable join reordering")
    p.set_defaults(join_reorder=True)

    p.add_argument("--allow-full-outer-reorder", action="store_true", help="When join reordering is enabled, allow FULL OUTER JOIN reordering (heuristic)")
    p.add_argument("--allow-left-reorder", action="store_true", help="When join reordering is enabled, allow LEFT JOIN reordering (heuristic)")

    p.add_argument("--report", help="Write a comparison report to this file (html or txt)")
    p.add_argument("--report-format", choices=["html", "txt"], default="html", help="Report format (default: html)")
    return p.parse_args(argv)


def read_from_stdin_two_parts():
    raw = sys.stdin.read()
    parts = re.split(r"^\s*---\s*$", raw, flags=re.M)
    if len(parts) != 2:
        raise ValueError("When using --stdin, provide exactly two parts separated by a line containing only ---")
    return parts[0].strip(), parts[1].strip()


def load_inputs(args):
    if args.strings:
        return args.strings[0], args.strings[1], "strings"
    if args.stdin:
        a, b = read_from_stdin_two_parts()
        return a, b, "stdin"
    if args.files and len(args.files) == 2:
        f1, f2 = args.files
        a = safe_read_file(f1)
        b = safe_read_file(f2)
        return a, b, "files"
    return None, None, None


def print_result_and_exit(result: dict, mode: str, ignore_ws: bool):
    print("=== SQL Compare ===")
    print(f"Whitespace-only equal: {'YES' if result['ws_equal'] else 'NO'}")
    print(f"Exact tokens equal   : {'YES' if result['exact_equal'] else 'NO'}")
    print(f"Canonical equal      : {'YES' if result['canonical_equal'] else 'NO'}")
    print("\n-- Summary of differences --")
    for line in result["summary"]:
        print(f"- {line}")
    print()

    if ignore_ws:
        print("---- Unified Diff (Whitespace-only normalized) ----")
        print(result["diff_ws"] if result["diff_ws"] else "(no differences)")
        print()
    if mode in ("both", "exact"):
        print("---- Unified Diff (Normalized) ----")
        print(result["diff_norm"] if result["diff_norm"] else "(no differences)")
        print()
    if mode in ("both", "canonical"):
        print("---- Unified Diff (Canonicalized) ----")
        print(result["diff_can"] if result["diff_can"] else "(no differences)")
        print()

    if mode == "exact":
        success = (result["ws_equal"] if ignore_ws else result["exact_equal"])
    else:
        success = result["canonical_equal"]
    sys.exit(0 if success else 1)


def generate_report(result: dict, mode: str, fmt: str, out_path: str, ignore_ws: bool):
    if fmt == "txt":
        lines = []
        lines.append("=== SQL Compare Report ===")
        lines.append(f"Whitespace-only equal: {'YES' if result['ws_equal'] else 'NO'}")
        lines.append(f"Exact tokens equal   : {'YES' if result['exact_equal'] else 'NO'}")
        lines.append(f"Canonical equal      : {'YES' if result['canonical_equal'] else 'NO'}")
        lines.append("")
        lines.append("-- Summary of differences --")
        for line in result["summary"]:
            lines.append(f"- {line}")
        lines.append("")
        if ignore_ws:
            lines.append("---- Unified Diff (Whitespace-only normalized) ----")
            lines.append(result["diff_ws"] if result["diff_ws"] else "(no differences)")
            lines.append("")
        if mode in ("both", "exact"):
            lines.append("---- Unified Diff (Normalized) ----")
            lines.append(result["diff_norm"] if result["diff_norm"] else "(no differences)")
            lines.append("")
        if mode in ("both", "canonical"):
            lines.append("---- Unified Diff (Canonicalized) ----")
            lines.append(result["diff_can"] if result["diff_can"] else "(no differences)")
            lines.append("")
        Path(out_path).write_text("\n".join(lines), encoding="utf-8")
        return

    # HTML (color-coded)
    hd = difflib.HtmlDiff(wrapcolumn=120)
    def mk(title, a, b, fromname, toname):
        table = hd.make_table(a.splitlines(), b.splitlines(), fromdesc=fromname, todesc=toname, context=True, numlines=3)
        return f"<h2>{title}</h2>\n{table}"

    sections = []
    sections.append("<h1>SQL Compare Report</h1>")
    sections.append("<h2>Summary</h2>")
    sections.append("<ul>")
    sections.append(f"<li>Whitespace-only equal: <b>{'YES' if result['ws_equal'] else 'NO'}</b></li>")
    sections.append(f"<li>Exact tokens equal: <b>{'YES' if result['exact_equal'] else 'NO'}</b></li>")
    sections.append(f"<li>Canonical equal: <b>{'YES' if result['canonical_equal'] else 'NO'}</b></li>")
    sections.append("</ul>")

    sections.append("""
    <h2>Summary of differences</h2>
    <ul>
    """ + "\n".join(f"<li>{line}</li>" for line in result["summary"]) + "</ul>")

    sections.append("""
    <div style="margin:8px 0;">
      <strong>Legend:</strong>
      <span style="background:#e6ffed;border:1px solid #34d058;padding:2px 6px;margin-left:6px;">Added</span>
      <span style="background:#ffeef0;border:1px solid #d73a49;padding:2px 6px;margin-left:6px;">Removed</span>
      <span style="background:#fff5b1;border:1px solid #d9c10c;padding:2px 6px;margin-left:6px;">Changed</span>
    </div>
    """)

    if ignore_ws:
        sections.append(mk("Whitespace-only Diff", result["ws_a"], result["ws_b"], "sql1(ws)", "sql2(ws)"))
    if mode in ("both", "exact"):
        sections.append(mk("Normalized Diff", result["norm_a"], result["norm_b"], "sql1(norm)", "sql2(norm)"))
    if mode in ("both", "canonical"):
        sections.append(mk("Canonicalized Diff", result["can_a"], result["can_b"], "sql1(canon)", "sql2(canon)"))

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>SQL Compare Report</title>
<style>
body {{ font-family: Segoe UI, Tahoma, Arial, sans-serif; margin: 16px; color: #111; }}
h1,h2 {{ margin: 12px 0; }}
table.diff {{ font-family: Consolas, monospace; font-size: 12px; border-collapse: collapse; width: 100%; }}
table.diff td, table.diff th {{ border: 1px solid #ddd; padding: 4px 6px; vertical-align: top; }}
table.diff thead th {{ background: #f6f8fa; }}
/* HtmlDiff cell classes */
.diff_add {{ background: #e6ffed; color: #1a7f37; }}   /* additions: green */
.diff_sub {{ background: #ffeef0; color: #cf222e; }}   /* deletions: red */
.diff_chg {{ background: #fff5b1; color: #4d2d00; }}   /* changes: amber */
/* Line number cols */
.diff_next, .diff_header {{ background: #f6f8fa; color: #57606a; }}
</style>
</head><body>
{''.join(sections)}
</body></html>"""
    Path(out_path).write_text(html, encoding="utf-8")


# =============================
# GUI
# =============================

class SQLCompareGUI:
    def __init__(self, root):
        self.root = root
        root.title("SQL Compare")
        root.geometry("980x780")

        self.sql1_path = tk.StringVar()
        self.sql2_path = tk.StringVar()
        self.mode = tk.StringVar(value="both")
        self.ignore_ws = tk.BooleanVar(value=False)
        self.enable_join = tk.BooleanVar(value=True)
        self.allow_full = tk.BooleanVar(value=False)
        self.allow_left = tk.BooleanVar(value=False)

        pad = {"padx": 8, "pady": 6}

        frm_top = ttk.Frame(root); frm_top.pack(fill="x", **pad)
        ttk.Label(frm_top, text="SQL File 1:").grid(row=0, column=0, sticky="w")
        e1 = ttk.Entry(frm_top, textvariable=self.sql1_path, width=90); e1.grid(row=0, column=1, sticky="we", padx=(8, 8))
        ttk.Button(frm_top, text="Browse...", command=self.browse1).grid(row=0, column=2)
        ttk.Label(frm_top, text="SQL File 2:").grid(row=1, column=0, sticky="w")
        e2 = ttk.Entry(frm_top, textvariable=self.sql2_path, width=90); e2.grid(row=1, column=1, sticky="we", padx=(8, 8))
        ttk.Button(frm_top, text="Browse...", command=self.browse2).grid(row=1, column=2)
        frm_top.columnconfigure(1, weight=1)

        frm_mode = ttk.Frame(root); frm_mode.pack(fill="x", **pad)
        ttk.Label(frm_mode, text="Mode:").pack(side="left")
        for text, val in [("Both", "both"), ("Exact", "exact"), ("Canonical", "canonical")]:
            ttk.Radiobutton(frm_mode, text=text, value=val, variable=self.mode).pack(side="left", padx=6)
        ttk.Checkbutton(frm_mode, text="Ignore whitespace differences", variable=self.ignore_ws).pack(side="left", padx=16)

        frm_flags = ttk.Frame(root); frm_flags.pack(fill="x", **pad)
        self.chk_enable_join = ttk.Checkbutton(frm_flags, text="Enable join reordering", variable=self.enable_join, command=self._toggle_join_options)
        self.chk_enable_join.pack(side="left", padx=6)
        self.chk_full = ttk.Checkbutton(frm_flags, text="Allow FULL OUTER JOIN reordering (heuristic)", variable=self.allow_full)
        self.chk_full.pack(side="left", padx=6)
        self.chk_left = ttk.Checkbutton(frm_flags, text="Allow LEFT JOIN reordering (heuristic)", variable=self.allow_left)
        self.chk_left.pack(side="left", padx=6)
        self._toggle_join_options()  # set initial state

        frm_btns = ttk.Frame(root); frm_btns.pack(fill="x", **pad)
        ttk.Button(frm_btns, text="Compare", command=self.do_compare).pack(side="left")
        ttk.Button(frm_btns, text="Copy Output", command=self.copy_output).pack(side="left", padx=6)
        ttk.Button(frm_btns, text="Clear", command=self.clear_output).pack(side="left", padx=6)
        ttk.Button(frm_btns, text="Save Report…", command=self.save_report).pack(side="left", padx=6)

        frm_out = ttk.Frame(root); frm_out.pack(fill="both", expand=True, **pad)
        self.txt = tk.Text(frm_out, wrap="none", font=("Consolas", 10))
        xscroll = ttk.Scrollbar(frm_out, orient="horizontal", command=self.txt.xview)
        yscroll = ttk.Scrollbar(frm_out, orient="vertical", command=self.txt.yview)
        self.txt.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        self.txt.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frm_out.rowconfigure(0, weight=1); frm_out.columnconfigure(0, weight=1)

        ttk.Label(root, text="Tip: CLI supports --strings/--stdin, --mode, --ignore-whitespace, --join-reorder/--no-join-reorder, --allow-full-outer-reorder, --allow-left-reorder, and --report.").pack(anchor="w", padx=8, pady=4)

        self.last_result = None  # cache for report generation

    def _toggle_join_options(self):
        # Enable/disable dependent flags based on global join toggle
        if self.enable_join.get():
            self.chk_full.state(['!disabled'])
            self.chk_left.state(['!disabled'])
        else:
            self.chk_full.state(['disabled'])
            self.chk_left.state(['disabled'])

    def browse1(self):
        path = filedialog.askopenfilename(title="Select SQL File 1",
                                          filetypes=[("SQL files", "*.sql *.txt"), ("All files", "*.*")])
        if path: self.sql1_path.set(path)

    def browse2(self):
        path = filedialog.askopenfilename(title="Select SQL File 2",
                                          filetypes=[("SQL files", "*.sql *.txt"), ("All files", "*.*")])
        if path: self.sql2_path.set(path)

    def clear_output(self):
        self.txt.delete("1.0", "end")

    def copy_output(self):
        try:
            content = self.txt.get("1.0", "end-1c")
            self.root.clipboard_clear(); self.root.clipboard_append(content)
            messagebox.showinfo("Copied", "Output copied to clipboard.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy: {e}")

    def do_compare(self):
        p1 = self.sql1_path.get().strip(); p2 = self.sql2_path.get().strip()
        if not p1 or not p2:
            messagebox.showwarning("Missing files", "Please select both SQL files."); return
        if not os.path.exists(p1) or not os.path.exists(p2):
            messagebox.showerror("File error", "One or both files do not exist."); return
        try:
            a = safe_read_file(p1)
            b = safe_read_file(p2)
            result = compare_sql(
                a, b,
                ignore_ws=self.ignore_ws.get(),
                enable_join_reorder=self.enable_join.get(),
                allow_full_outer=self.allow_full.get(),
                allow_left=self.allow_left.get()
            )
            self.last_result = result
            self.render_result(result, self.mode.get(), self.ignore_ws.get())
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def render_result(self, result: dict, mode: str, ignore_ws: bool):
        self.clear_output()
        lines = []
        lines.append("=== SQL Compare ===")
        lines.append(f"Whitespace-only equal: {'YES' if result['ws_equal'] else 'NO'}")
        lines.append(f"Exact tokens equal   : {'YES' if result['exact_equal'] else 'NO'}")
        lines.append(f"Canonical equal      : {'YES' if result['canonical_equal'] else 'NO'}")
        lines.append("")
        lines.append("-- Summary of differences --")
        for line in result["summary"]:
            lines.append(f"- {line}")
        lines.append("")
        if ignore_ws:
            lines.append("---- Unified Diff (Whitespace-only normalized) ----")
            lines.append(result["diff_ws"] if result["diff_ws"] else "(no differences)"); lines.append("")
        if mode in ("both", "exact"):
            lines.append("---- Unified Diff (Normalized) ----")
            lines.append(result["diff_norm"] if result["diff_norm"] else "(no differences)"); lines.append("")
        if mode in ("both", "canonical"):
            lines.append("---- Unified Diff (Canonicalized) ----")
            lines.append(result["diff_can"] if result["diff_can"] else "(no differences)"); lines.append("")
        self.txt.insert("1.0", "\n".join(lines))

    def save_report(self):
        if not self.last_result:
            messagebox.showwarning("No results", "Run a comparison first."); return
        path = filedialog.asksaveasfilename(
            title="Save Report",
            defaultextension=".html",
            filetypes=[("HTML report", "*.html"), ("Text report", "*.txt")]
        )
        if not path:
            return
        fmt = "html" if path.lower().endswith(".html") else "txt"
        try:
            mode = self.mode.get()
            ignore_ws = self.ignore_ws.get()
            generate_report(self.last_result, mode, fmt, path, ignore_ws)
            messagebox.showinfo("Saved", f"Report saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save report:\n{e}")


def maybe_launch_gui(args_parsed) -> bool:
    """Return True if GUI launched and program should exit afterward."""
    if (args_parsed.files is None or len(args_parsed.files) == 0) and not args_parsed.strings and not args_parsed.stdin:
        if not TK_AVAILABLE:
            print("Tkinter is not available. Provide CLI inputs, or install Python with Tk support.", file=sys.stderr)
            sys.exit(2)
        root = tk.Tk()
        SQLCompareGUI(root)
        root.mainloop()
        return True
    return False


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    if maybe_launch_gui(args): return
    a, b, src = load_inputs(args)
    if a is None or b is None:
        print("Provide two files, or --strings, or --stdin; or run with no args to open the GUI.", file=sys.stderr)
        sys.exit(2)
    result = compare_sql(
        a, b,
        ignore_ws=args.ignore_whitespace,
        enable_join_reorder=args.join_reorder,
        allow_full_outer=args.allow_full_outer_reorder,
        allow_left=args.allow_left_reorder
    )
    if args.report:
        try:
            generate_report(result, args.mode, args.report_format, args.report, args.ignore_whitespace)
            print(f"[Report] Saved to: {args.report}")
        except Exception as e:
            print(f"[Report] Failed: {e}", file=sys.stderr)
            sys.exit(2)
    print_result_and_exit(result, args.mode, args.ignore_whitespace)


if __name__ == "__main__":
    main()
