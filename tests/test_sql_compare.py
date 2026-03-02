import unittest
from sql_compare import canonicalize_joins, build_difference_summary

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
        expected = "SELECT * FROM t1 FULL JOIN t2 ON y FULL JOIN t3 ON x"
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


class TestBuildDifferenceSummary(unittest.TestCase):
    def test_no_differences(self):
        sql = "SELECT a, b FROM t WHERE x = 1"
        summary = build_difference_summary(
            sql, sql, sql, sql,
            ["SELECT", "a", ",", "b", "FROM", "t", "WHERE", "x", "=", "1"],
            ["SELECT", "a", ",", "b", "FROM", "t", "WHERE", "x", "=", "1"],
            enable_join_reorder=True, allow_full_outer=False, allow_left=False
        )
        self.assertEqual(summary, ["No structural differences detected beyond normalization."])

    def test_select_differences(self):
        sql_a = "SELECT a, b FROM t"
        sql_b = "SELECT a, c FROM t"
        summary = build_difference_summary(
            sql_a, sql_b, sql_a, sql_b,
            ["SELECT", "a", ",", "b", "FROM", "t"],
            ["SELECT", "a", ",", "c", "FROM", "t"],
            enable_join_reorder=True, allow_full_outer=False, allow_left=False
        )
        self.assertIn("SELECT list differs: items only in SQL1: 1", summary)
        self.assertIn("SELECT list differs: items only in SQL2: 1", summary)
        self.assertTrue(any("Token-level changes" in s for s in summary))

    def test_select_order_differs(self):
        sql_a = "SELECT a, b FROM t"
        sql_b = "SELECT b, a FROM t"
        summary = build_difference_summary(
            sql_a, sql_b, sql_a, sql_b,
            ["SELECT", "a", ",", "b", "FROM", "t"],
            ["SELECT", "b", ",", "a", "FROM", "t"],
            enable_join_reorder=True, allow_full_outer=False, allow_left=False
        )
        self.assertIn("SELECT list order differs (same items, different order).", summary)
        self.assertTrue(any("Token-level changes" in s for s in summary))

    def test_where_differences(self):
        sql_a = "SELECT a FROM t WHERE x = 1 AND y = 2"
        sql_b = "SELECT a FROM t WHERE x = 1 AND z = 3"
        summary = build_difference_summary(
            sql_a, sql_b, sql_a, sql_b,
            [], [],
            enable_join_reorder=True, allow_full_outer=False, allow_left=False
        )
        self.assertIn("WHERE AND terms differ: terms only in SQL1: 1", summary)
        self.assertIn("WHERE AND terms differ: terms only in SQL2: 1", summary)

    def test_where_order_differs(self):
        sql_a = "SELECT a FROM t WHERE x = 1 AND y = 2"
        sql_b = "SELECT a FROM t WHERE y = 2 AND x = 1"
        summary = build_difference_summary(
            sql_a, sql_b, sql_a, sql_b,
            [], [],
            enable_join_reorder=True, allow_full_outer=False, allow_left=False
        )
        self.assertIn("WHERE AND term order differs (same terms, different order).", summary)

    def test_join_differences(self):
        sql_a = "SELECT a FROM t JOIN x ON t.id=x.id"
        sql_b = "SELECT a FROM t JOIN y ON t.id=y.id"
        summary = build_difference_summary(
            sql_a, sql_b, sql_a, sql_b,
            [], [],
            enable_join_reorder=True, allow_full_outer=False, allow_left=False
        )
        self.assertIn("Reorderable JOIN components differ: 1 only in SQL1.", summary)
        self.assertIn("Reorderable JOIN components differ: 1 only in SQL2.", summary)

    def test_join_order_differs(self):
        sql_a = "SELECT a FROM t JOIN x ON t.id=x.id JOIN y ON t.id=y.id"
        sql_b = "SELECT a FROM t JOIN y ON t.id=y.id JOIN x ON t.id=x.id"
        summary = build_difference_summary(
            sql_a, sql_b, sql_a, sql_b,
            [], [],
            enable_join_reorder=True, allow_full_outer=False, allow_left=False
        )
        self.assertIn("Reorderable JOIN segment order differs (same components, different order).", summary)

    def test_join_reorder_disabled(self):
        sql_a = "SELECT a FROM t JOIN x ON t.id=x.id JOIN y ON t.id=y.id"
        sql_b = "SELECT a FROM t JOIN y ON t.id=y.id JOIN x ON t.id=x.id"
        summary = build_difference_summary(
            sql_a, sql_b, sql_a, sql_b,
            [], [],
            enable_join_reorder=False, allow_full_outer=False, allow_left=False
        )
        self.assertIn("Join reordering is disabled; join order is considered significant in comparisons.", summary)


if __name__ == '__main__':
    unittest.main()
