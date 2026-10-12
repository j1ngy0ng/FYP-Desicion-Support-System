import tempfile
import unittest
from pathlib import Path

import numpy as np

from scripts.analyse_human_study import bootstrap_mean, percentile_ci, sha256


class HumanStudyAnalysisTests(unittest.TestCase):
    def test_constant_participant_metric_has_exact_bootstrap_interval(self):
        values = np.array([0.625, 0.625, 0.625])
        low, high = bootstrap_mean(values, np.random.default_rng(42), 100)
        self.assertEqual((low, high), (0.625, 0.625))

    def test_percentile_interval_uses_prespecified_bounds(self):
        low, high = percentile_ci(np.arange(1, 101, dtype=float))
        self.assertAlmostEqual(low, 3.475)
        self.assertAlmostEqual(high, 97.525)

    def test_sha256_is_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.txt"
            path.write_bytes(b"human-study-evidence")
            self.assertEqual(
                sha256(path),
                "236bd8ca9a4a7b85f71cd1610b92db15decf197c1b0f470e850ede1bafc26958",
            )


if __name__ == "__main__":
    unittest.main()
