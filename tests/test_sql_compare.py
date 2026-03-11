import unittest
from sql_compare import canonicalize_joins, parse_args, strip_sql_comments, normalize_sql

class TestCanonicalizeJoins(unittest.TestCase):
    def test_basic_inner_join_reorder(self):
        """Inner joins should be reordered alphabetically by table name."""
        sql = "SELECT * FROM t1 JOIN t3 ON t1.id=t3.id JOIN t2 ON t1.id=t2.id"
        expected = "SELECT * FROM t1 JOIN t2 ON t1.id=t2.id JOIN t3 ON t1.id=t3.id"
        self.assertEqual(canonicalize_joins(sql), expected)

    def test_explicit_inner_join_reorder(self):
        """INNER JOIN keywords should be treated same as JOIN."""
        sql = "SELECT * FROM t1 INNER JOIN t3 ON t1.id=t3.id INNER JOIN t2 ON t1.id=t2.id"
        expected = "SELECT * FROM t1 JOIN t2 ON t1.id=t2.id JOIN t3 ON t1.id=t3.id"
        self.assertEqual(canonicalize_joins(sql), expected)

    def test_left_join_no_reorder(self):
        """Left joins should NOT be reordered by default."""
        sql = "SELECT * FROM t1 LEFT JOIN t3 ON t1.id=t3.id LEFT JOIN t2 ON t1.id=t2.id"
        self.assertEqual(canonicalize_joins(sql), sql)

    def test_left_join_allow_reorder(self):
        """Left joins SHOULD be reordered if allow_left is True."""
        sql = "SELECT * FROM t1 LEFT JOIN t3 ON t1.id=t3.id LEFT JOIN t2 ON t1.id=t2.id"
        expected = "SELECT * FROM t1 LEFT JOIN t2 ON t1.id=t2.id LEFT JOIN t3 ON t1.id=t3.id"
        self.assertEqual(canonicalize_joins(sql, allow_left=True), expected)

    def test_mixed_joins_barrier(self):
        """Reorderable joins should not cross non-reorderable join barriers."""
        # t3 and t2 are INNER (reorderable), t4 is LEFT (barrier)
        sql = "SELECT * FROM t1 JOIN t3 ON x JOIN t2 ON y LEFT JOIN t4 ON z"
        # t3 and t2 should swap.
        expected = "SELECT * FROM t1 JOIN t2 ON y JOIN t3 ON x LEFT JOIN t4 ON z"
        self.assertEqual(canonicalize_joins(sql), expected)

    def test_mixed_joins_barrier_2(self):
        """Reorderable joins should not cross non-reorderable join barriers (case 2)."""
        # t1 -> LEFT t2 -> JOIN t4 -> JOIN t3
        # t4 and t3 are after the barrier t2. They should be reordered among themselves.
        sql = "SELECT * FROM t1 LEFT JOIN t2 ON x JOIN t4 ON y JOIN t3 ON z"
        expected = "SELECT * FROM t1 LEFT JOIN t2 ON x JOIN t3 ON z JOIN t4 ON y"
        self.assertEqual(canonicalize_joins(sql), expected)

    def test_full_outer_join_no_reorder(self):
        """FULL OUTER joins should NOT be reordered by default."""
        sql = "SELECT * FROM t1 FULL JOIN t3 ON x FULL JOIN t2 ON y"
        self.assertEqual(canonicalize_joins(sql), sql)

    def test_full_outer_join_allow_reorder(self):
        """FULL OUTER joins SHOULD be reordered if allow_full_outer is True."""
        sql = "SELECT * FROM t1 FULL JOIN t3 ON x FULL JOIN t2 ON y"
        # Note: 'FULL JOIN' is normalized to 'FULL JOIN' (OUTER is optional/removed if not handled?)
        # Let's check implementation: seg_type replaces " OUTER", so "FULL OUTER JOIN" -> "FULL JOIN".
        # Then _rebuild uses seg_type + " JOIN". So "FULL JOIN".
        # If input has "FULL OUTER JOIN", output will have "FULL JOIN".
        # We should expect "FULL JOIN".
        expected = "SELECT * FROM t1 FULL JOIN t2 ON y FULL JOIN t3 ON x"
        # However, if input is already "FULL JOIN", it stays "FULL JOIN".
        self.assertEqual(canonicalize_joins(sql, allow_full_outer=True), expected)

    def test_cross_join_reorder(self):
        """CROSS JOIN should be reordered."""
        sql = "SELECT * FROM t1 CROSS JOIN t3 CROSS JOIN t2"
        expected = "SELECT * FROM t1 CROSS JOIN t2 CROSS JOIN t3"
        self.assertEqual(canonicalize_joins(sql), expected)

    def test_natural_join_reorder(self):
        """NATURAL JOIN should be reordered."""
        sql = "SELECT * FROM t1 NATURAL JOIN t3 NATURAL JOIN t2"
        expected = "SELECT * FROM t1 NATURAL JOIN t2 NATURAL JOIN t3"
        self.assertEqual(canonicalize_joins(sql), expected)


class TestParseArgs(unittest.TestCase):
    def test_parse_args_no_arguments(self):
        """parse_args with no arguments should return default values."""
        args = parse_args([])
        with self.subTest(param="files"):
            self.assertEqual(args.files, [])
        with self.subTest(param="strings"):
            self.assertIsNone(args.strings)
        with self.subTest(param="stdin"):
            self.assertFalse(args.stdin)
        with self.subTest(param="mode"):
            self.assertEqual(args.mode, 'both')
        with self.subTest(param="ignore_whitespace"):
            self.assertFalse(args.ignore_whitespace)
        with self.subTest(param="join_reorder"):
            self.assertTrue(args.join_reorder)
        with self.subTest(param="allow_full_outer_reorder"):
            self.assertFalse(args.allow_full_outer_reorder)
        with self.subTest(param="allow_left_reorder"):
            self.assertFalse(args.allow_left_reorder)
        with self.subTest(param="report"):
            self.assertIsNone(args.report)
        with self.subTest(param="report_format"):
            self.assertEqual(args.report_format, 'html')

class TestNormalizeSql(unittest.TestCase):
    def test_basic_normalization(self):
        """Test collapsing whitespace and uppercasing outside quotes."""
        sql = "   select  * \n from \t my_table   "
        expected = "SELECT * FROM MY_TABLE"
        self.assertEqual(normalize_sql(sql), expected)

    def test_remove_comments(self):
        """Test removing single-line and block comments."""
        sql = "SELECT * /* block comment */ FROM t1 -- line comment\n WHERE id = 1"
        expected = "SELECT * FROM T1 WHERE ID = 1"
        self.assertEqual(normalize_sql(sql), expected)

    def test_remove_trailing_semicolon(self):
        """Test removing trailing semicolon."""
        sql = "SELECT * FROM my_table;"
        expected = "SELECT * FROM MY_TABLE"
        self.assertEqual(normalize_sql(sql), expected)

        sql_with_spaces = "SELECT * FROM my_table ;  "
        expected_with_spaces = "SELECT * FROM MY_TABLE"
        self.assertEqual(normalize_sql(sql_with_spaces), expected_with_spaces)

    def test_preserve_quotes(self):
        """Test that content inside quotes is NOT uppercased."""
        sql = "SELECT 'lower_case', \"double_quote\", `backtick`, [bracket] FROM t1"
        expected = "SELECT 'lower_case', \"double_quote\", `backtick`, [bracket] FROM T1"
        self.assertEqual(normalize_sql(sql), expected)

    def test_remove_outer_parentheses(self):
        """Test removing outer parentheses."""
        sql = "(((SELECT * FROM my_table)))"
        expected = "SELECT * FROM MY_TABLE"
        self.assertEqual(normalize_sql(sql), expected)

    def test_complex_normalization(self):
        """Test a combination of normalization steps."""
        sql = """
        -- A complex query
        (
            SELECT id, name /* internal block */
            FROM users
            WHERE status = 'active'
        ) ;
        """
        expected = "SELECT ID, NAME FROM USERS WHERE STATUS = 'active'"
        self.assertEqual(normalize_sql(sql), expected)
class TestStripSqlComments(unittest.TestCase):
    def test_single_line_comment(self):
        """Should strip single line comment starting with --."""
        sql = "-- this is a comment\nSELECT * FROM t1;"
        expected = "\nSELECT * FROM t1;"
        self.assertEqual(strip_sql_comments(sql), expected)

    def test_inline_comment(self):
        """Should strip inline comment at the end of a line."""
        sql = "SELECT * FROM t1; -- comment here"
        expected = "SELECT * FROM t1; "
        self.assertEqual(strip_sql_comments(sql), expected)

    def test_block_comment_single_line(self):
        """Should strip block comment on a single line."""
        sql = "SELECT /* comment */ * FROM t1;"
        expected = "SELECT  * FROM t1;"
        self.assertEqual(strip_sql_comments(sql), expected)

    def test_block_comment_multi_line(self):
        """Should strip block comment spanning multiple lines."""
        sql = "SELECT /* \n multi \n line \n comment \n */ * FROM t1;"
        expected = "SELECT  * FROM t1;"
        self.assertEqual(strip_sql_comments(sql), expected)

    def test_multiple_comments(self):
        """Should strip multiple comments of different types."""
        sql = "/* start */ SELECT * FROM t1; -- end comment"
        expected = " SELECT * FROM t1; "
        self.assertEqual(strip_sql_comments(sql), expected)

    def test_no_comments(self):
        """Should return the same string if there are no comments."""
        sql = "SELECT * FROM t1;"
        expected = "SELECT * FROM t1;"
        self.assertEqual(strip_sql_comments(sql), expected)

if __name__ == '__main__':

    unittest.main()
