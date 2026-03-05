
## $(date +%Y-%m-%d) - [Optimize `top_level_find_kw` avoiding O(N^2) string slicing]
**Learning:** Checking string slices with `re.match` inside manual character-by-character state machines (e.g., `re.match(..., sql[i:])`) leads to massive O(N^2) bottlenecks on large strings due to repeated string slicing and regex compilation overhead per character.
**Action:** Use `re.finditer` to quickly jump to candidate match indices in O(N) time, and advance the state machine index `i` up to that point (`match.start()`) to validate it, bypassing expensive linear scanning and slicing overhead.
