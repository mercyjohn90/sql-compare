## 2026-03-04 - [XSS in HtmlDiff HTML Report]
**Vulnerability:** XSS vulnerability found in HTML report generation. The `make_table` method of Python's `difflib.HtmlDiff` module does not escape user-provided inputs in `fromdesc` and `todesc`. Also, dynamically injected data like title and summary strings were unescaped in HTML markup.
**Learning:** Functions that generate HTML like `difflib.HtmlDiff.make_table` or manually concatenated strings are often missing implicit escaping mechanisms.
**Prevention:** Explicitly use `html.escape()` on all dynamically provided strings (like table descriptors, titles, labels, or error messages) before passing them to markup builders or inserting into string templates.
