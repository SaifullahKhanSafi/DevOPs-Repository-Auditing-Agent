"""Scoring tests: only one-to-one human labels can count as true positives."""

import unittest

from scripts.evaluate import metrics


class MetricTests(unittest.TestCase):
    def test_precision_and_recall(self):
        result = metrics(
            {"violations": [{}, {}, {}]},
            {"true_positive_indices": [0, 2], "known_violation_count": 4},
        )
        self.assertAlmostEqual(result["precision"], 2 / 3)
        self.assertEqual(result["recall"], 0.5)
        self.assertEqual(result["false_positives"], 1)
        self.assertEqual(result["false_negatives"], 2)

    def test_duplicate_labels_rejected(self):
        with self.assertRaises(ValueError):
            metrics(
                {"violations": [{}]}, {"true_positive_indices": [0, 0], "known_violation_count": 2}
            )

    def test_empty_healthy_report(self):
        result = metrics(
            {"violations": []}, {"true_positive_indices": [], "known_violation_count": 0}
        )
        self.assertIsNone(result["precision"])
        self.assertIsNone(result["recall"])
