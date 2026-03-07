## 2024-06-13 - XSS in HTML Report Generation
**Vulnerability:** Cross-Site Scripting (XSS) via unescaped string interpolations in HTML report generator (`sql_compare.py`). The summary strings and difference descriptions were injected directly into the HTML using f-strings and `.join()` without HTML encoding.
**Learning:** `difflib.HtmlDiff` handles escaping for the diff content itself, but manual f-string injection and its `make_table` arguments (`fromdesc`, `todesc`) do not escape HTML natively. This is a common pattern when wrapping library outputs in custom HTML templates.
**Prevention:** Always wrap dynamically generated or user-provided strings with `html.escape()` when injecting them into an HTML response or file, even if a library is managing parts of the HTML.
