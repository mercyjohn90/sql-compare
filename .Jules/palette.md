## 2024-05-24 - Empty states and disabled actions prevent user confusion
**Learning:** Pairing a helpful empty-state placeholder (like "Select files and click Compare to see results here.") with disabled states for output-dependent action buttons significantly improves UX. It clearly communicates when output is unavailable and prevents invalid user actions before comparison completes.
**Action:** Always verify if action buttons dependent on data have an appropriate `disabled` state managed dynamically, and pair this with clear, descriptive empty-state placeholders in output areas.
