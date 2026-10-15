"""Machine-check provenance/status of public agent rehearsal (NOT external E2E)."""
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "evals/agent-runs/2026-10-15-gpt6-in-session.md"
PROTOCOL = ROOT / "evals/agent-test-protocol.md"


class AgentEvidenceIntegrityTests(unittest.TestCase):
    def test_18_synthetic_responses_with_no_external_pass_claim(self):
        text = LOG.read_text(encoding="utf-8")
        blocks = re.findall(r"(?m)^## (A[0-9]{2}) · (audit|rewrite|create|compare)$", text)
        self.assertEqual(len(blocks), 18)
        self.assertEqual(len(set(blocks)), 18)
        self.assertEqual(text.count("**Фактический ответ GPT-6 в сессии:**"), 18)
        self.assertEqual(text.count("SELF_REVIEW_PASS"), 18)
        self.assertEqual(text.count("независимый агентский прогон: NOT_RUN"),18)
        self.assertIn("НЕ установлен",text)
        self.assertIn("0 независимых прогонов",text)

    def test_procedure_explicitly_requires_independent_agent(self):
        text=PROTOCOL.read_text(encoding="utf-8")
        for needed in ("NOT_RUN", "SELF_REVIEW_PASS", "независимый",
                       "дословный ответ", "skill_commit"):
            with self.subTest(needed=needed):
                self.assertIn(needed,text)


if __name__=="__main__":
    unittest.main()
