from __future__ import annotations

import unittest

from scripts.ai_flow.action_contract import group_actions


class ActionContractTests(unittest.TestCase):
    def test_copyable_routing_command_groups_as_command(self) -> None:
        groups = {
            item["id"]: item
            for item in group_actions(
                [
                    {
                        "id": "configure_economy_provider_command",
                        "label": "Copy provider command",
                        "kind": "command",
                        "command": "patchbay config --set-key providers.cheap_writer.command --set-value <command>",
                        "safe": True,
                    }
                ]
            )
        }

        self.assertIn("commands", groups)
        self.assertIn("configure_economy_provider_command", groups["commands"]["action_ids"])
        self.assertNotIn("routing", groups)

    def test_local_agent_command_fallback_can_stay_in_routing(self) -> None:
        groups = {
            item["id"]: item
            for item in group_actions(
                [
                    {
                        "id": "configure_reasonix_command",
                        "label": "Configure Reasonix",
                        "kind": "local_agent",
                        "message": "configure reasonix command",
                        "command": "patchbay config --set-key commands.reasonix --set-value reasonix",
                        "safe": True,
                    }
                ]
            )
        }

        self.assertIn("routing", groups)
        self.assertIn("configure_reasonix_command", groups["routing"]["action_ids"])
        self.assertNotIn("commands", groups)

    def test_setup_command_keeps_setup_group(self) -> None:
        groups = {
            item["id"]: item
            for item in group_actions(
                [
                    {
                        "id": "install_skill",
                        "label": "Update Codex Skill",
                        "kind": "command",
                        "command": "patchbay skill install codex",
                        "safe": True,
                    }
                ]
            )
        }

        self.assertIn("setup", groups)
        self.assertIn("install_skill", groups["setup"]["action_ids"])
        self.assertNotIn("commands", groups)

    def test_plain_command_groups_as_command(self) -> None:
        groups = {
            item["id"]: item
            for item in group_actions(
                [
                    {
                        "id": "copy_metric_command",
                        "label": "Copy metrics command",
                        "kind": "command",
                        "command": "patchbay metrics latest --json",
                        "safe": True,
                    }
                ]
            )
        }

        self.assertIn("commands", groups)
        self.assertIn("copy_metric_command", groups["commands"]["action_ids"])


if __name__ == "__main__":
    unittest.main()
