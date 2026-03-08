import unittest
import tempfile
import os
from pathlib import Path
from sql_compare import generate_report

class TestSecurity(unittest.TestCase):
    def test_xss_in_html_report_escaping(self):
        # Create a mock result payload with XSS attempts
        xss_payload = "<script>alert('xss')</script>"
        mock_result = {
            "ws_equal": True,
            "exact_equal": True,
            "canonical_equal": True,
            "ws_a": "SELECT *",
            "ws_b": "SELECT *",
            "norm_a": "SELECT *",
            "norm_b": "SELECT *",
            "can_a": "SELECT *",
            "can_b": "SELECT *",
            "summary": [f"Summary payload {xss_payload}"],
            "diff_ws": "diff",
            "diff_norm": "diff",
            "diff_can": "diff"
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = os.path.join(temp_dir, "report.html")

            # The mode doesn't matter much here since we just want to verify generate_report
            # runs without exceptions and escapes the output correctly.
            generate_report(mock_result, mode="both", fmt="html", out_path=out_path, ignore_ws=True)

            # Read back generated HTML
            content = Path(out_path).read_text(encoding="utf-8")

            # Ensure the raw <script> tag is NOT present
            self.assertNotIn(xss_payload, content)

            # Ensure the escaped version IS present
            import html
            escaped_payload = html.escape(xss_payload)
            self.assertIn(f"Summary payload {escaped_payload}", content)

if __name__ == '__main__':
    unittest.main()
