import unittest
from sql_compare import canonicalize_joins, clause_end_index, tokenize, top_level_find_kw

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


class TestTopLevelFindKw(unittest.TestCase):
    def test_keyword_inside_single_quotes(self):
        """Keywords inside single quotes should be ignored."""
        sql = "SELECT a FROM t WHERE b = 'WHERE' AND c = 1"
        # The WHERE inside quotes should be ignored, should find the real WHERE
        result = top_level_find_kw(sql, "WHERE")
        self.assertEqual(result, sql.index("WHERE"))
        # If we search for AND starting after WHERE, should find AND after the quoted text
        and_pos = top_level_find_kw(sql, "AND", result + 1)
        self.assertEqual(and_pos, sql.index("AND"))

    def test_keyword_inside_double_quotes(self):
        """Keywords inside double quotes should be ignored."""
        sql = 'SELECT a FROM t WHERE b = "WHERE" AND c = 1'
        result = top_level_find_kw(sql, "WHERE")
        self.assertEqual(result, sql.index("WHERE"))

    def test_keyword_inside_brackets(self):
        """Keywords inside bracket identifiers should be ignored."""
        sql = "SELECT a FROM [WHERE] WHERE b = 1"
        # [WHERE] is a bracketed identifier, should find the real WHERE after it
        result = top_level_find_kw(sql, "WHERE")
        self.assertEqual(result, sql.rindex("WHERE"))

    def test_keyword_inside_backticks(self):
        """Keywords inside backtick identifiers should be ignored."""
        sql = "SELECT a FROM `WHERE` WHERE b = 1"
        # `WHERE` is a backticked identifier, should find the real WHERE after it
        result = top_level_find_kw(sql, "WHERE")
        self.assertEqual(result, sql.rindex("WHERE"))

    def test_keyword_inside_parentheses(self):
        """Keywords inside parenthesized subqueries should be ignored."""
        sql = "SELECT * FROM t1 JOIN (SELECT * FROM t2 WHERE b = 1) ON a = b WHERE a = 1"
        # The WHERE inside the subquery should be ignored, should find the last WHERE
        result = top_level_find_kw(sql, "WHERE")
        self.assertEqual(result, sql.rindex("WHERE"))

    def test_start_offset(self):
        """Should respect start parameter for subsequent lookups."""
        sql = "SELECT a FROM t WHERE b = 1 AND c = 2 AND d = 3"
        # Find first AND
        first_and = top_level_find_kw(sql, "AND")
        self.assertEqual(first_and, sql.index("AND"))
        # Find second AND starting after first
        second_and = top_level_find_kw(sql, "AND", first_and + 1)
        self.assertGreater(second_and, first_and)
        self.assertEqual(second_and, sql.index("AND", first_and + 1))

    def test_word_boundary(self):
        """Should match only whole words, not substrings."""
        sql = "SELECT a FROM whereabouts WHERE b = 1"
        # Should not match 'WHERE' inside 'whereabouts', should find actual WHERE
        result = top_level_find_kw(sql, "WHERE")
        self.assertEqual(result, sql.index("WHERE"))
        # Should return -1 if keyword not found
        result = top_level_find_kw(sql, "LIMIT")
        self.assertEqual(result, -1)

    def test_escaped_single_quotes(self):
        """Should handle escaped single quotes correctly."""
        sql = "SELECT * FROM t WHERE a = 'it''s' AND b = 1"
        # The doubled single quote is an escape sequence, should stay inside the string
        result = top_level_find_kw(sql, "AND")
        self.assertEqual(result, sql.index("AND"))

    def test_escaped_double_quotes(self):
        """Should handle escaped double quotes correctly."""
        sql = 'SELECT * FROM t WHERE a = "say ""hello""" AND b = 1'
        # The doubled double quote is an escape sequence, should stay inside the string
        result = top_level_find_kw(sql, "AND")
        self.assertEqual(result, sql.index("AND"))

    def test_case_insensitivity(self):
        """Keyword search parameter is uppercased, but SQL matching is case-sensitive."""
        sql = "SELECT a FROM t WHERE b = 1"
        # Search with lowercase parameter should find uppercase WHERE in SQL
        result = top_level_find_kw(sql, "where")
        self.assertEqual(result, sql.index("WHERE"))
        # But lowercase WHERE in SQL won't be found
        sql_lower = "SELECT a FROM t where b = 1"
        result = top_level_find_kw(sql_lower, "WHERE")
        self.assertEqual(result, -1)

    def test_nested_parentheses(self):
        """Should handle multiple levels of nested parentheses."""
        sql = "SELECT * FROM t1 WHERE a IN (SELECT x FROM (SELECT y FROM t2 WHERE z = 1)) AND b = 2"
        # Should find the first top-level WHERE, ignoring the one inside nested subquery
        result = top_level_find_kw(sql, "WHERE")
        self.assertEqual(result, sql.index("WHERE"))
        # Should find the top-level AND
        result = top_level_find_kw(sql, "AND")
        self.assertEqual(result, sql.index("AND"))


class TestClauseEndIndex(unittest.TestCase):
    def test_no_terminators(self):
        """Should return length of string if no terminators found."""
        sql = "SELECT * FROM my_table JOIN other_table ON a = b"
        self.assertEqual(clause_end_index(sql, 0), len(sql))

    def test_single_terminator(self):
        """Should return index of the terminator."""
        sql = "SELECT * FROM my_table WHERE a = 1"
        # 'WHERE' starts at index 25
        self.assertEqual(clause_end_index(sql, 0), sql.index("WHERE"))

        sql = "SELECT * FROM my_table GROUP BY a"
        self.assertEqual(clause_end_index(sql, 0), sql.index("GROUP BY"))

    def test_multiple_terminators(self):
        """Should return index of the first terminator found in the string."""
        sql = "SELECT * FROM my_table WHERE a = 1 GROUP BY a ORDER BY a"
        # Even though GROUP BY and ORDER BY exist, WHERE is first
        self.assertEqual(clause_end_index(sql, 0), sql.index("WHERE"))

        # If we start after WHERE, we should find GROUP BY
        start_after_where = sql.index("WHERE") + 5
        self.assertEqual(clause_end_index(sql, start_after_where), sql.index("GROUP BY"))

    def test_terminator_inside_subquery(self):
        """Should ignore terminators inside parentheses."""
        sql = "SELECT * FROM t1 JOIN (SELECT * FROM t2 WHERE b = 1) ON a = b WHERE a = 1"
        # The WHERE inside the subquery should be ignored.
        # We want the index of the last WHERE.
        self.assertEqual(clause_end_index(sql, 0), sql.rindex("WHERE"))

    def test_terminator_inside_quotes(self):
        """Should ignore terminators inside quotes or brackets."""
        sql = "SELECT * FROM t1 WHERE a = 'WHERE' GROUP BY b"
        # The 'WHERE' inside quotes should be ignored. We should find 'WHERE' keyword
        self.assertEqual(clause_end_index(sql, 0), sql.index("WHERE"))

        sql2 = "SELECT * FROM t1 JOIN [WHERE] u ON a = b GROUP BY b"
        # [WHERE] is a bracketed identifier; the parser enters mode='bracket' and ignores it
        self.assertEqual(clause_end_index(sql2, 0), sql2.index("GROUP BY"))

        sql3 = "SELECT * FROM t1 JOIN u ON a = `WHERE` GROUP BY b"
        self.assertEqual(clause_end_index(sql3, 0), sql3.index("GROUP BY"))

    def test_different_start_indices(self):
        """Should correctly offset the search based on start index."""
        sql = "SELECT * FROM my_table WHERE a = 1"
        self.assertEqual(clause_end_index(sql, 0), sql.index("WHERE"))

        # If start is past WHERE, it shouldn't find it
        self.assertEqual(clause_end_index(sql, sql.index("WHERE") + 1), len(sql))
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


class TestClauseEndIndex(unittest.TestCase):
    def test_no_terminators(self):
        """Should return length of string if no terminators found."""
        sql = "SELECT * FROM my_table JOIN other_table ON a = b"
        self.assertEqual(clause_end_index(sql, 0), len(sql))

    def test_single_terminator(self):
        """Should return index of the first terminator."""
        test_cases = [
            ("with WHERE clause", "SELECT * FROM my_table WHERE a = 1", "WHERE"),
            ("with GROUP BY clause", "SELECT * FROM my_table GROUP BY a", "GROUP BY"),
        ]
        for description, sql, terminator in test_cases:
            with self.subTest(description=description):
                self.assertEqual(clause_end_index(sql, 0), sql.index(terminator))

    def test_multiple_terminators(self):
        """Should return index of the first terminator from start."""
        sql = "SELECT * FROM my_table WHERE a = 1 GROUP BY a ORDER BY a"
        self.assertEqual(clause_end_index(sql, 0), sql.index("WHERE"))

        start_after_where = sql.index("WHERE") + len("WHERE")
        self.assertEqual(clause_end_index(sql, start_after_where), sql.index("GROUP BY"))

    def test_terminator_inside_subquery(self):
        """Should ignore terminators inside nested parentheses."""
        sql = "SELECT * FROM t1 JOIN (SELECT * FROM t2 WHERE b = 1) ON a = b WHERE a = 1"
        self.assertEqual(clause_end_index(sql, 0), sql.rindex("WHERE"))

    def test_terminator_inside_quotes(self):
        """Should ignore terminators that appear inside quoted strings."""
        test_cases = [
            ("in single quotes", "SELECT * FROM t1 WHERE a = 'WHERE' GROUP BY b", "WHERE"),
            ("in brackets", "SELECT * FROM t1 JOIN u ON a = '[WHERE]' GROUP BY b", "GROUP BY"),
            ("in backticks", "SELECT * FROM t1 JOIN u ON a = `WHERE` GROUP BY b", "GROUP BY"),
        ]
        for description, sql, expected_terminator in test_cases:
            with self.subTest(description=description):
                self.assertEqual(clause_end_index(sql, 0), sql.index(expected_terminator))

    def test_different_start_indices(self):
        """Should honor starting position when searching for terminators."""
        sql = "SELECT * FROM my_table WHERE a = 1"
        self.assertEqual(clause_end_index(sql, 0), sql.index("WHERE"))
        self.assertEqual(clause_end_index(sql, sql.index("WHERE") + 1), len(sql))

if __name__ == '__main__':

    unittest.main()
