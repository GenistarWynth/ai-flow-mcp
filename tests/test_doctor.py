from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class DoctorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="patchbay-doctor-"))
        subprocess.run(["git", "init"], cwd=str(self.tmp), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "patchbay@example.test"], cwd=str(self.tmp), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Patchbay Test"], cwd=str(self.tmp), capture_output=True, check=True)
        (self.tmp / "README.md").write_text("# test\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(self.tmp), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(self.tmp), capture_output=True, check=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unified_doctor_reports_missing_init_without_mcp_probe(self) -> None:
        from scripts.ai_flow.doctor import run_doctor

        result = run_doctor(self.tmp, include_mcp=False)

        self.assertFalse(result["ok"])
        self.assertTrue(result["checks"]["repo"]["git_repo"])
        self.assertIn(".ai/patchbay.example.toml", result["checks"]["repo"]["missing_files"])
        self.assertTrue(result["checks"]["mcp"]["skipped"])
        self.assertTrue(any("patchbay init" in action for action in result["next_actions"]))

    def test_unified_doctor_accepts_initialized_project(self) -> None:
        from scripts.ai_flow import service
        from scripts.ai_flow.doctor import run_doctor

        service.init_project(self.tmp)
        result = run_doctor(self.tmp, include_mcp=False, skill_path=self.tmp / "skills")

        self.assertTrue(result["checks"]["repo"]["ok"])
        self.assertTrue(result["checks"]["config"]["ok"])
        self.assertTrue(result["checks"]["cli"]["ok"])
        self.assertTrue(result["checks"]["skill"]["source_exists"])
        self.assertFalse(result["checks"]["skill"]["installed"])
        self.assertFalse(result["ok"])
        self.assertTrue(any("skill install codex" in action for action in result["next_actions"]))


if __name__ == "__main__":
    unittest.main()
