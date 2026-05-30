from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
        self.assertIn("patchbay setup for Claude Desktop", result["files"]["SKILL.md"])
        self.assertIn("configure reasonix command", result["files"]["SKILL.md"])
        self.assertIn("command_not_ready", result["files"]["SKILL.md"])
        self.assertIn("install patchbay for Gemini CLI", result["files"]["references/install.md"])
        self.assertIn("configure reasonix command", result["files"]["references/install.md"])
        self.assertIn("configure_reasonix_command", result["files"]["references/install.md"])

    def test_bundled_skill_matches_install_template(self) -> None:
        template_root = PROJECT_ROOT / "scripts" / "ai_flow" / "skill_templates" / "patchbay"
        bundled_root = PROJECT_ROOT / "skills" / "patchbay"
        for relative in (
            Path("SKILL.md"),
            Path("references/install.md"),
        ):
            self.assertEqual(
                (template_root / relative).read_text(encoding="utf-8"),
                (bundled_root / relative).read_text(encoding="utf-8"),
                f"{relative.as_posix()} drifted between the install template and bundled skill",
            )

    def test_package_data_includes_skill_template_bundle(self) -> None:
        data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        package_data = data["tool"]["setuptools"]["package-data"]["ai_flow"]

        self.assertIn("skill_templates/**", package_data)
        for required in (
            "SKILL.md",
            "agents/openai.yaml",
            "references/install.md",
        ):
            self.assertTrue((PROJECT_ROOT / "scripts" / "ai_flow" / "skill_templates" / "patchbay" / required).exists())

    def test_skill_install_copies_bundle(self) -> None:
        from scripts.ai_flow.skill_install import run_skill_install

        target = self.tmp / "skills-root"
        result = run_skill_install(self.tmp, path=target)

        destination = target / "patchbay"
        self.assertTrue(result["installed"])
        self.assertEqual(Path(result["destination"]), destination)
        self.assertTrue((destination / "SKILL.md").exists())
        self.assertTrue((destination / "agents" / "openai.yaml").exists())
        self.assertIn("patchbay setup for Claude Desktop", (destination / "SKILL.md").read_text(encoding="utf-8"))

    def test_skill_install_dry_run_does_not_copy(self) -> None:
        from scripts.ai_flow.skill_install import run_skill_install

        target = self.tmp / "skills-root"
        result = run_skill_install(self.tmp, path=target, dry_run=True)

        self.assertTrue(result["dry_run"])
        self.assertFalse((target / "patchbay").exists())

    def test_cli_skill_doctor_json_reports_ready_state(self) -> None:
        script = PROJECT_ROOT / "scripts" / "patchbay"
        target = self.tmp / "skills-root"
        completed = subprocess.run(
            ["python", str(script), "skill", "doctor", "codex", "--path", str(target), "--json"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["ok"])
        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "not_installed")

    def test_skill_doctor_reports_source_and_install_state(self) -> None:
        from scripts.ai_flow.skill_install import run_skill_doctor, run_skill_install

        target = self.tmp / "skills-root"
        before = run_skill_doctor(self.tmp, path=target)
        self.assertTrue(before["ok"])
        self.assertFalse(before["ready"])
        self.assertEqual(before["status"], "not_installed")
        self.assertTrue(before["source_exists"])
        self.assertFalse(before["installed"])
        self.assertTrue(any("skill install codex" in action for action in before["next_actions"]))

        run_skill_install(self.tmp, path=target)
        after = run_skill_doctor(self.tmp, path=target)
        self.assertTrue(after["ok"])
        self.assertTrue(after["ready"])
        self.assertEqual(after["status"], "installed")
        self.assertTrue(after["installed"])
        self.assertEqual(Path(after["destination"]), target / "patchbay")
        self.assertEqual(after["next_actions"], [])


if __name__ == "__main__":
    unittest.main()
