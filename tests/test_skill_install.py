from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path


class SkillInstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="patchbay-skill-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_skill_print_includes_required_files(self) -> None:
        from scripts.ai_flow.skill_install import run_skill_print

        result = run_skill_print(self.tmp)

        self.assertIn("SKILL.md", result["files"])
        self.assertIn("agents/openai.yaml", result["files"])
        self.assertIn("references/install.md", result["files"])
        self.assertIn("patchbay_agent", result["files"]["SKILL.md"])

    def test_skill_install_copies_bundle(self) -> None:
        from scripts.ai_flow.skill_install import run_skill_install

        target = self.tmp / "skills-root"
        result = run_skill_install(self.tmp, path=target)

        destination = target / "patchbay"
        self.assertTrue(result["installed"])
        self.assertEqual(Path(result["destination"]), destination)
        self.assertTrue((destination / "SKILL.md").exists())
        self.assertTrue((destination / "agents" / "openai.yaml").exists())

    def test_skill_install_dry_run_does_not_copy(self) -> None:
        from scripts.ai_flow.skill_install import run_skill_install

        target = self.tmp / "skills-root"
        result = run_skill_install(self.tmp, path=target, dry_run=True)

        self.assertTrue(result["dry_run"])
        self.assertFalse((target / "patchbay").exists())


if __name__ == "__main__":
    unittest.main()
