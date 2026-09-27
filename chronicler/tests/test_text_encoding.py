import locale
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chronicler.app import runner


class TextEncodingTest(unittest.TestCase):
    def test_utf8_and_local_lines_are_decoded_independently_even_in_utf8_mode(self):
        data = "UTF-8 中文\n".encode("utf-8") + "本地错误\n".encode("cp936")
        with patch.object(locale, "getencoding", return_value="cp936"), \
                patch.object(locale, "getpreferredencoding", return_value="utf-8"):
            self.assertEqual("UTF-8 中文\n本地错误\n", runner._decode_bytes(data))

    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "Windows PowerShell required")
    def test_powershell_profile_preserves_content_and_roundtrips_unicode(self):
        script = Path(__file__).resolve().parents[2] / "scripts" / "fix-powershell-utf8.ps1"
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profile.ps1"
            profile.write_text("# keep\n$global:ExistingSetting='中文'\n", encoding="utf-8")
            for _ in range(2):
                subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                str(script), "-ProfilePath", str(profile)], check=True, capture_output=True)
            text = profile.read_text(encoding="utf-8-sig")
            self.assertIn("$global:ExistingSetting='中文'", text)
            self.assertEqual(text.count("# BEGIN Chronicler UTF-8"), 1)
            content = Path(temporary) / "content.txt"
            content.write_text("中文编码验证", encoding="utf-8")
            command = '. $args[0]; Get-Content -LiteralPath $args[1]; $args[2] | python -c "import sys;print(sys.stdin.read(),end=\'\')"'
            # File paths and Unicode are script arguments, never interpolated into command text.
            probe = Path(temporary) / "probe.ps1"
            probe.write_text(command, encoding="utf-8")
            result = subprocess.run(["powershell", "-NoProfile", "-File", str(probe), str(profile),
                                     str(content), "中文管道验证"], check=True, capture_output=True)
            output = result.stdout.decode("utf-8")
            self.assertIn("中文编码验证", output)
            self.assertIn("中文管道验证", output)


class CognitiveCompletionTest(unittest.TestCase):
    def test_summary_without_completed_state_is_failed(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(runner.projects, "shadow_dir", return_value=Path(temporary)):
            run = {"id": 27, "project_id": 2, "task_type": "project_cognitive_maintainer", "input_snapshot": {"repo_head": "abc"}}
            self.assertTrue(runner._cognitive_completion_error(run))

    def test_completion_requires_current_run_record_and_matching_source_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".cognitive-state.yaml").write_text("source:\n  commit: abc\nmaintenance:\n  last_run: runs/current.md\n", encoding="utf-8")
            (root / "runs").mkdir()
            record = root / "runs" / "current.md"
            record.write_text("---\nrun_id: 26\nstatus: success\ntarget_commit: abc\n---\n", encoding="utf-8")
            run = {"id": 27, "project_id": 2, "task_type": "project_cognitive_maintainer", "input_snapshot": {"repo_head": "abc"}}
            with patch.object(runner.projects, "shadow_dir", return_value=root):
                self.assertTrue(runner._cognitive_completion_error(run))
                record.write_text("---\nrun_id: 27\nstatus: success\ntarget_commit: abc\n---\n", encoding="utf-8")
                self.assertEqual("", runner._cognitive_completion_error(run))
                run["input_snapshot"]["repo_head"] = "different"
                self.assertTrue(runner._cognitive_completion_error(run))
