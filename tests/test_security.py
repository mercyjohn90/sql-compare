import unittest
import os
import tempfile
from sql_compare import generate_report

class TestSecurity(unittest.TestCase):
    def test_xss_in_report_summary(self):
        """Verify that HTML characters in the summary are escaped to prevent XSS."""
        result = {
            "ws_equal": False,
            "exact_equal": False,
            "canonical_equal": False,
            "summary": ["<script>alert('XSS Summary')</script>"],
            "diff_ws": "",
            "diff_norm": "",
            "diff_can": "",
            "ws_a": "", "ws_b": "",
            "norm_a": "", "norm_b": "",
            "can_a": "", "can_b": ""
        }

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            out_path = f.name

        try:
            generate_report(result, "canonical", "html", out_path, True)

            with open(out_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertNotIn("<script>", content, "Script tag was not escaped in the HTML output.")
            self.assertIn("&lt;script&gt;alert(&#x27;XSS Summary&#x27;)&lt;/script&gt;", content)
        finally:
            os.unlink(out_path)

if __name__ == "__main__":
    unittest.main()
