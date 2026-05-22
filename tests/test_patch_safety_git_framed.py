from __future__ import annotations

import unittest

from scripts.ai_flow.errors import SafetyError
from scripts.ai_flow.safety import paths_from_patch, validate_patch_safety

# String constants so the test source file itself has no column-0 raw
# "--- ", "+++ ", or "diff --git " lines that could confuse an old apply parser.
_DIFF_GIT = "diff --git "
_MINUS = "--- "
_PLUS = "+++ "
_AT = "@@ "
_SP = " "  # context-line prefix in unified-diff hunk bodies


class PatchSafetyGitFramedTests(unittest.TestCase):
    """Regression coverage for the git-framed-only diff safety parser.

    The old ``paths_from_patch`` stripped every line before classifying it,
    which caused hunk-body text containing nested ``---`` / ``+++`` /
    ``diff --git`` fragments to be misread as file-headers or new sections.
    These tests confirm the fix and the new bare-diff rejection.
    """

    # ── helper ──────────────────────────────────────────────────────────
    @staticmethod
    def _git_framed_patch(
        src: str,
        dst: str,
        *hunk_lines: str,
        extra_header: str | None = None,
        index_line: str | None = None,
    ) -> str:
        """Build a minimal git-framed unified diff fixture."""
        header = [
            f"{_DIFF_GIT}a/{src} b/{dst}",
        ]
        if index_line is not None:
            header.append(index_line)
        header.append(f"{_MINUS}a/{src}")
        header.append(f"{_PLUS}b/{dst}")
        if extra_header is not None:
            header.append(extra_header)
        header.append(f"{_AT}-1,0 +1,{len(hunk_lines)} @@")
        return "\n".join(header + list(hunk_lines))

    # ── tests ───────────────────────────────────────────────────────────

    def test_nested_diff_text_in_hunk_passes(self) -> None:
        """Git-framed patch whose hunk body contains lines that look like
        inner diff headers — the old parser would misclassify them."""
        patch = self._git_framed_patch(
            "foo.txt",
            "foo.txt",
            # Context lines whose TEXT (after the leading space) looks like:
            #   --- a/evil
            #   +++ b/evil
            #   diff --git a/evil b/evil
            _SP + _MINUS + "a/evil",
            _SP + _PLUS + "b/evil",
            _SP + _DIFF_GIT + "a/evil b/evil",
            _SP + "normal context line",
            "+an added line",
            "-a removed line",
        )

        # Must not raise — the nested-looking text is inside a hunk body.
        validate_patch_safety(patch)

        # Only the real header paths are returned; nothing from the hunk body.
        paths = paths_from_patch(patch)
        self.assertEqual(paths, ["foo.txt"])

    def test_real_traversal_rejected(self) -> None:
        """Git-framed patch with '..' in the real header paths is still rejected."""
        patch = self._git_framed_patch(
            "../escape",
            "../escape",
            "+bad",
        )

        with self.assertRaises(SafetyError) as ctx:
            validate_patch_safety(patch)
        self.assertIn("traversal", str(ctx.exception).lower())

    def test_real_absolute_path_rejected(self) -> None:
        """Git-framed patch with an absolute /etc/passwd path is still rejected."""
        # Place the leading-slash path directly in the diff --git line
        # (without an a/ prefix) so it is extracted and validated.
        patch = "\n".join([
            f"{_DIFF_GIT}/etc/passwd /etc/passwd",
            f"{_MINUS}/etc/passwd",
            f"{_PLUS}/etc/passwd",
            f"{_AT}-0,0 +1 @@",
            "+bad",
        ])
        with self.assertRaises(SafetyError) as ctx:
            validate_patch_safety(patch)
        self.assertIn("absolute", str(ctx.exception).lower())

    def test_real_dotgit_rejected(self) -> None:
        """Git-framed patch touching .git is still rejected."""
        patch = self._git_framed_patch(
            ".git/config",
            ".git/config",
            "+bad",
        )
        with self.assertRaises(SafetyError) as ctx:
            validate_patch_safety(patch)
        self.assertIn(".git", str(ctx.exception).lower())

    def test_real_dotenv_rejected(self) -> None:
        """Git-framed patch touching .env is still rejected."""
        patch = self._git_framed_patch(
            ".env",
            ".env",
            "+SECRET=bad",
        )
        with self.assertRaises(SafetyError) as ctx:
            validate_patch_safety(patch)
        self.assertIn("environment file", str(ctx.exception).lower())

    def test_real_secret_name_rejected(self) -> None:
        """Git-framed patch touching a secret-like path is still rejected."""
        patch = self._git_framed_patch(
            "config/private_key.pem",
            "config/private_key.pem",
            "+bad",
        )
        with self.assertRaises(SafetyError) as ctx:
            validate_patch_safety(patch)
        self.assertIn("secret-like", str(ctx.exception).lower())

    def test_bare_unified_diff_rejected(self) -> None:
        """Patch with ---/+++ headers but no diff --git is rejected as unsupported."""
        # No _DIFF_GIT line — just the bare unified-diff headers.
        patch = "\n".join([
            f"{_MINUS}a/normal.txt",
            f"{_PLUS}b/normal.txt",
            f"{_AT}-1 +1 @@",
            _SP + "old",
            "+new",
        ])

        with self.assertRaises(SafetyError) as ctx:
            validate_patch_safety(patch)
        msg = str(ctx.exception).lower()
        self.assertIn("git-framed", msg)

        # paths_from_patch on a bare diff returns an empty list.
        self.assertEqual(paths_from_patch(patch), [])

    def test_bare_diff_without_any_diffgit_but_no_bare_headers_is_caught_by_paths_check(self) -> None:
        """Patch with no diff --git AND no ---/+++ headers at all falls
        through to the 'no recognizable paths' check."""
        patch = "just some random text\nnot a diff at all\n"
        with self.assertRaises(SafetyError) as ctx:
            validate_patch_safety(patch)
        self.assertIn("recognizable", str(ctx.exception).lower())

    def test_empty_patch_rejected(self) -> None:
        """Empty patch is still rejected early."""
        with self.assertRaises(SafetyError) as ctx:
            validate_patch_safety("")
        self.assertIn("empty", str(ctx.exception).lower())

    def test_rename_in_header_yields_paths(self) -> None:
        """Rename-only sections inside a diff --git frame are parsed correctly."""
        patch = "\n".join([
            f"{_DIFF_GIT}a/old_name.py b/new_name.py",
            "similarity index 100%",
            "rename from old_name.py",
            "rename to new_name.py",
        ])
        paths = paths_from_patch(patch)
        self.assertIn("old_name.py", paths)
        self.assertIn("new_name.py", paths)

    def test_multi_file_patch_isolates_sections(self) -> None:
        """A multi-file git-framed patch isolates paths per section; hunk
        body text in the first section does not leak into the second."""
        patch = "\n".join([
            # First file
            f"{_DIFF_GIT}a/first.txt b/first.txt",
            f"{_MINUS}a/first.txt",
            f"{_PLUS}b/first.txt",
            f"{_AT}-1,3 +1,5 @@",
            _SP + _MINUS + "a/evil",       # nested in hunk body — ignored
            _SP + _PLUS + "b/evil",
            # Second file
            f"{_DIFF_GIT}a/second.txt b/second.txt",
            f"{_MINUS}a/second.txt",
            f"{_PLUS}b/second.txt",
            f"{_AT}-1 +1 @@",
            _SP + "safe",
        ])
        paths = paths_from_patch(patch)
        self.assertEqual(paths, ["first.txt", "second.txt"])


if __name__ == "__main__":
    unittest.main()
