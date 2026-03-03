import unittest
from sql_compare import canonicalize_joins, tokenize

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


class TestTokenize(unittest.TestCase):
    def test_tokenize_scenarios(self):
        """Test the tokenize function with various SQL inputs."""
        test_cases = [
            # description, sql_string, expected_tokens
            ("Basic SELECT query",
             "SELECT a, b FROM table1 WHERE id = 1",
             ['SELECT', 'a', ',', 'b', 'FROM', 'table1', 'WHERE', 'id', '=', '1']),

            # Note: E'...' parses as E, '...' while E"..." parses as E"..."
            ("Single, double, and E-quoted strings",
             "SELECT 'string', E'string2', \"col 1\", E\"esc\"",
             ['SELECT', "'string'", ',', 'E', "'string2'", ',', '"col 1"', ',', 'E"esc"']),

            # Note: 'it''s' is parsed as 'it', 's' by the regex currently.
            # This test ensures no unexpected regressions.
            ("Strings with escaped single quotes",
             "SELECT 'it''s'",
             ['SELECT', "'it'", "'s'"]),

            ("Bracketed and backticked identifiers",
             "SELECT [my table], `my col`",
             ['SELECT', '[my table]', ',', '`my col`']),

            ("Integer and float numbers",
             "SELECT 123, 45.67",
             ['SELECT', '123', ',', '45.67']),

            ("Multi-character operators",
             "SELECT a <= b, c >= d, e <> f, g != h, i := j, k -> l, m::n",
             ['SELECT', 'a', '<=', 'b', ',', 'c', '>=', 'd', ',',
              'e', '<>', 'f', ',', 'g', '!=', 'h', ',',
              'i', ':=', 'j', ',', 'k', '->', 'l', ',', 'm', '::', 'n']),

            ("Single-character operators and punctuation",
             "SELECT a + b - c * d / e % f",
             ['SELECT', 'a', '+', 'b', '-', 'c', '*', 'd', '/', 'e', '%', 'f']),

            ("Whitespace (spaces, tabs, newlines) should be ignored",
             "SELECT \n\ta  \r\n  b",
             ['SELECT', 'a', 'b'])
        ]

        for description, sql, expected in test_cases:
            with self.subTest(description=description):
                self.assertEqual(tokenize(sql), expected)

if __name__ == '__main__':
    unittest.main()
