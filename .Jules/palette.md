## 2024-05-24 - explicit empty state and interactive buttons

**Learning:** In Tkinter, explicit UX cues are needed for initial states. When an output widget starts empty, a placeholder text ("Select files and click Compare to see results here.") gives helpful guidance to the user. Additionally, explicitly disabling action buttons (`btn_copy`, `btn_clear`, `btn_save`) using `.state(['disabled'])` prevents invalid actions until output is actually available.

**Action:** Whenever a view or text widget is initialized that expects data, use an empty-state placeholder text. Also ensure that interactive buttons related to that data are initialized with `.state(['disabled'])` and only enabled with `.state(['!disabled'])` once the data is present.
