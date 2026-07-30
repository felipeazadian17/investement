import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from investement.domain import SignalAction
from investement.orchestration import (
    AgentFinding,
    EvidenceReference,
    InvestmentCommittee,
    JsonlAuditLog,
    JsonMemoryStore,
    WorkflowEngine,
    WorkflowStep,
)


def finding(agent, score, veto=False):
    return AgentFinding(
        agent=agent,
        subject="AAPL",
        score=score,
        confidence=0.8,
        thesis=f"Evidence-backed view from {agent}",
        evidence=(
            EvidenceReference(
                source="test",
                reference=f"fixture://{agent}",
                observed_at=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ),
        risk_veto=veto,
    )


class OrchestrationTests(unittest.TestCase):
    def test_committee_records_dissent(self):
        decision = InvestmentCommittee().decide(
            (finding("fundamental", 0.9), finding("technical", -0.4), finding("risk", 0.2))
        )
        self.assertEqual(decision.action, SignalAction.HOLD)
        self.assertIn("technical", decision.dissenting_agents)
        self.assertLess(decision.confidence, 0.8)

    def test_risk_veto_blocks_action(self):
        decision = InvestmentCommittee().decide(
            (finding("fundamental", 0.9), finding("risk", 0.5, veto=True))
        )
        self.assertEqual(decision.action, SignalAction.HOLD)
        self.assertEqual(decision.risk_vetoed_by, ("risk",))
        self.assertEqual(decision.effective_weights["risk"], 0.0)

    def test_committee_uses_explicit_factor_weights(self):
        decision = InvestmentCommittee().decide(
            (
                finding("fundamental", 0.7),
                finding("relative-valuation", 0.5),
                finding("technical", 0.1),
                finding("risk", 0.0),
            )
        )

        self.assertAlmostEqual(sum(decision.effective_weights.values()), 1.0)
        self.assertEqual(decision.effective_weights["fundamental"], 0.55)
        self.assertEqual(decision.effective_weights["technical"], 0.20)
        self.assertEqual(decision.effective_weights["risk"], 0.0)

    def test_committee_rejects_duplicate_agent_votes(self):
        with self.assertRaisesRegex(ValueError, "unique agents"):
            InvestmentCommittee().decide(
                (finding("fundamental", 0.5), finding("fundamental", 0.6))
            )

    def test_workflow_resolves_dependencies_and_audits_hash_chain(self):
        with tempfile.TemporaryDirectory() as temporary:
            audit = JsonlAuditLog(Path(temporary) / "events.jsonl")
            steps = (
                WorkflowStep("second", lambda context: context.outputs["first"] + 1, ("first",)),
                WorkflowStep("first", lambda context: context.inputs["value"] * 2),
            )
            result = WorkflowEngine(steps, audit).run(
                {"value": 3},
                as_of=datetime(2024, 1, 1, tzinfo=UTC),
                run_id="run-1",
            )
            self.assertEqual(result.execution_order, ("first", "second"))
            self.assertEqual(result.outputs["second"], 7)
            self.assertTrue(audit.verify())
            self.assertEqual(len(audit.read()), 6)

    def test_audit_detects_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "events.jsonl"
            audit = JsonlAuditLog(path)
            audit.append("run-1", "test", {"value": 1})
            event = json.loads(path.read_text(encoding="utf-8"))
            event["payload"]["value"] = 2
            path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            self.assertFalse(audit.verify())

    def test_core_audit_log_redacts_credentials_without_the_auditor_facade(self):
        with tempfile.TemporaryDirectory() as temporary:
            audit = JsonlAuditLog(Path(temporary) / "events.jsonl")
            audit.append(
                "run-1",
                "broker.failed",
                {"consumerKey": "private", "nested": {"clientId": "also-private"}},
            )

            payload = audit.read()[0].payload

        self.assertEqual(payload["consumerKey"], "[REDACTED]")
        self.assertEqual(payload["nested"]["clientId"], "[REDACTED]")

    def test_workflow_rejects_dependency_cycles_before_execution(self):
        with self.assertRaisesRegex(ValueError, "dependency cycle"):
            WorkflowEngine(
                (
                    WorkflowStep("first", lambda context: None, ("second",)),
                    WorkflowStep("second", lambda context: None, ("first",)),
                )
            )

    def test_memory_store_is_atomic_and_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            memory = JsonMemoryStore(Path(temporary))
            memory.save("thesis.AAPL", {"status": "active"})
            self.assertEqual(memory.load("thesis.AAPL").value["status"], "active")
            self.assertEqual(memory.list_keys(), ("thesis.AAPL",))
            with self.assertRaises(ValueError):
                memory.save("../escape", {"bad": True})


if __name__ == "__main__":
    unittest.main()
