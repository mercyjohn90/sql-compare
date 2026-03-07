## 2024-05-24 - Fast regex lookahead in parsing loops

**Learning:** Character-by-character parsing loops (like `top_level_find_kw`) that repeatedly slice strings for regex checks (`re.match(pattern, string[i:])`) create severe O(N²) performance bottlenecks due to constant string allocation on large files, which is particularly detrimental when parsing large, generated SQL strings.

**Action:** To optimize state-tracking text parsing loops (e.g., checking quotes or nesting levels), use `re.finditer` for fast regex lookahead to jump directly to candidate match indices. Then, advance the state-machine up to that exact index to validate it, bypassing expensive linear scanning and O(N²) string slicing.
