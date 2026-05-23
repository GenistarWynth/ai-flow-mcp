"""Tests for free phase-to-provider routing and role validation."""

from __future__ import annotations

import unittest

from scripts.ai_flow.adapters import (
    PLANNERS,
    PROVIDERS,
    REVIEWERS,
    WRITERS,
    provider_roles,
    provider_supports_phase,
)


class CrossPhaseRoutingTest(unittest.TestCase):
    def test_providers_declares_all_role_entries(self) -> None:
        """Every id in PLANNERS/WRITERS/REVIEWERS/FIXERS is known to PROVIDERS."""
        all_ids = set(PLANNERS) | set(WRITERS) | set(REVIEWERS)
        for pid in all_ids:
            with self.subTest(provider_id=pid):
                self.assertIn(pid, PROVIDERS, f"{pid} missing from PROVIDERS")

    def test_plan_providers_have_plan_role(self) -> None:
        for pid in PLANNERS:
            with self.subTest(provider_id=pid):
                self.assertTrue(provider_supports_phase(pid, "plan"),
                                f"{pid} should support plan phase")

    def test_write_providers_have_write_role(self) -> None:
        for pid in WRITERS:
            with self.subTest(provider_id=pid):
                self.assertTrue(provider_supports_phase(pid, "write"),
                                f"{pid} should support write phase")

    def test_review_providers_have_review_role(self) -> None:
        for pid in REVIEWERS:
            with self.subTest(provider_id=pid):
                self.assertTrue(provider_supports_phase(pid, "review"),
                                f"{pid} should support review phase")

    def test_reasonix_supports_write_and_fix(self) -> None:
        roles = provider_roles("reasonix_cli")
        self.assertIn("write", roles)
        self.assertIn("fix", roles)
        self.assertNotIn("plan", roles)
        self.assertNotIn("review", roles)

    def test_mock_supports_all_roles(self) -> None:
        roles = provider_roles("mock")
        self.assertIn("plan", roles)
        self.assertIn("write", roles)
        self.assertIn("review", roles)
        self.assertIn("fix", roles)

    def test_unknown_provider_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            provider_roles("nonexistent_provider")

    def test_non_model_phases_always_pass(self) -> None:
        """test and apply phases have no role requirement — always pass."""
        self.assertTrue(provider_supports_phase("reasonix_cli", "test"))
        self.assertTrue(provider_supports_phase("reasonix_cli", "apply"))
        self.assertTrue(provider_supports_phase("mock", "test"))
        self.assertTrue(provider_supports_phase("mock", "apply"))

    def test_claude_cli_supports_plan_and_review(self) -> None:
        roles = provider_roles("claude_cli")
        self.assertIn("plan", roles)
        self.assertIn("review", roles)

    def test_codex_cli_supports_plan_and_review(self) -> None:
        roles = provider_roles("codex_cli")
        self.assertIn("plan", roles)
        self.assertIn("review", roles)

    def test_gemini_cli_supports_plan_and_review(self) -> None:
        roles = provider_roles("gemini_cli")
        self.assertIn("plan", roles)
        self.assertIn("review", roles)

    def test_review_registry_uses_review_callable(self) -> None:
        """codex_cli in REVIEWERS points to run_codex_reviewer (not planner)."""
        from scripts.ai_flow.adapters.codex_reviewer import run_codex_reviewer
        self.assertIs(REVIEWERS["codex_cli"], run_codex_reviewer)

    def test_plan_registry_uses_plan_callable(self) -> None:
        """codex_cli in PLANNERS points to run_codex_planner (not reviewer)."""
        from scripts.ai_flow.adapters.codex_planner import run_codex_planner
        self.assertIs(PLANNERS["codex_cli"], run_codex_planner)


if __name__ == "__main__":
    unittest.main()
