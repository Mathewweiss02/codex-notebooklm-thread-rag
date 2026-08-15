from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from notebooklm_replica_plan import ReplicaPlanError, build_replica_plan  # noqa: E402


class ReplicaPlanTests(unittest.TestCase):
    def test_models_incremental_replica_cost_without_live_mutation(self) -> None:
        plan = build_replica_plan(
            source_parts=147,
            source_limit=300,
            notebook_limit=500,
            reserve=60,
            existing_notebooks=2,
            current_retrieval_notebooks=1,
            pool_sizes=[1, 2, 4, 8, 8],
        )
        self.assertEqual(plan["steadyCapacityPerReplica"], 240)
        self.assertEqual(plan["poolSizes"], [1, 2, 4, 8])
        rows = {row["retrievalPoolSize"]: row for row in plan["plans"]}
        self.assertEqual(rows[1]["newReplicaCount"], 0)
        self.assertEqual(rows[2]["newReplicaCount"], 1)
        self.assertEqual(rows[4]["newReplicaCount"], 3)
        self.assertEqual(rows[8]["newReplicaCount"], 7)
        self.assertEqual(rows[8]["steadyHeadroomPerReplica"], 93)
        self.assertEqual(rows[8]["aggregateSourceCopies"], 1176)
        self.assertTrue(all(row["capacitySafe"] for row in rows.values()))

    def test_rejects_a_replica_that_cannot_preserve_reserve(self) -> None:
        with self.assertRaises(ReplicaPlanError):
            build_replica_plan(
                source_parts=241,
                source_limit=300,
                notebook_limit=500,
                reserve=60,
                existing_notebooks=2,
                current_retrieval_notebooks=1,
                pool_sizes=[1],
            )

    def test_rejects_invalid_pool_or_notebook_relationship(self) -> None:
        with self.assertRaises(ReplicaPlanError):
            build_replica_plan(
                source_parts=10,
                source_limit=300,
                notebook_limit=500,
                reserve=60,
                existing_notebooks=1,
                current_retrieval_notebooks=2,
                pool_sizes=[1],
            )


if __name__ == "__main__":
    unittest.main()
