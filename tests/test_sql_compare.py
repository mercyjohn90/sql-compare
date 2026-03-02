import unittest
from sql_compare import canonicalize_joins, normalize_sql

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


class TestCompareSql(unittest.TestCase):
    def test_exact_equal(self):
        sql = "SELECT * FROM t1"
        res = compare_sql(sql, sql)
        with self.subTest(check="ws_equal"):
            self.assertTrue(res['ws_equal'])
        with self.subTest(check="exact_equal"):
            self.assertTrue(res['exact_equal'])
        with self.subTest(check="canonical_equal"):
            self.assertTrue(res['canonical_equal'])

    def test_ws_difference(self):
        sql1 = "SELECT * FROM t1"
        sql2 = "SELECT  *   FROM   t1"
        res = compare_sql(sql1, sql2)
        self.assertTrue(res['ws_equal'])
        self.assertTrue(res['exact_equal'])
        self.assertTrue(res['canonical_equal'])

    def test_case_difference(self):
        sql1 = "SELECT * FROM t1"
        sql2 = "select * from t1"
        res = compare_sql(sql1, sql2)
        self.assertTrue(res['exact_equal'])
        self.assertTrue(res['canonical_equal'])

    def test_canonical_equal_only(self):
        sql1 = "SELECT * FROM t1 JOIN t2 ON t1.id=t2.id JOIN t3 ON t1.id=t3.id"
        sql2 = "SELECT * FROM t1 JOIN t3 ON t1.id=t3.id JOIN t2 ON t1.id=t2.id"
        res = compare_sql(sql1, sql2)
        self.assertFalse(res['exact_equal'])
        self.assertTrue(res['canonical_equal'])

    def test_not_equal(self):
        sql1 = "SELECT * FROM t1"
        sql2 = "SELECT * FROM t2"
        res = compare_sql(sql1, sql2)
        self.assertFalse(res['exact_equal'])
        self.assertFalse(res['canonical_equal'])

    def test_disable_join_reorder(self):
        sql1 = "SELECT * FROM t1 JOIN t2 ON t1.id=t2.id JOIN t3 ON t1.id=t3.id"
        sql2 = "SELECT * FROM t1 JOIN t3 ON t1.id=t3.id JOIN t2 ON t1.id=t2.id"
        res = compare_sql(sql1, sql2, enable_join_reorder=False)
        self.assertFalse(res['canonical_equal'])


if __name__ == '__main__':
    unittest.main()


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
        cases = {
            "with_semicolon": "SELECT * FROM my_table;",
            "with_semicolon_and_spaces": "SELECT * FROM my_table ;  ",
        }
        expected = "SELECT * FROM MY_TABLE"
        for name, sql in cases.items():
            with self.subTest(name=name):
                self.assertEqual(normalize_sql(sql), expected)

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
