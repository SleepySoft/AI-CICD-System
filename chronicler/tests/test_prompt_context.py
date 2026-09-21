import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chronicler.app import prompt_context, registry


class PromptContextTest(unittest.TestCase):
    def test_build_context_covers_contract_and_separates_baselines(self):
        project = {
            "id": 7,
            "name": "sample",
            "git_url": "https://example.com/sample.git",
            "default_branch": "main",
            "shadow_repo": "https://example.com/sample-shadow.git",
            "ci_url": "",
            "last_synced_at": 1758412800,
            "last_sync_error": "",
        }
        harness = {"report_mode": "stdout", "timeout_sec": 30}
        change = {
            "baseline_run_id": None,
            "change_summary": {"state": "changed", "base_revision": "a" * 40},
            "formatted_context": "- 基线：aaaaaaaaaa",
        }

        with tempfile.TemporaryDirectory() as temp:
            shadow_dir = Path(temp)
            (shadow_dir / ".cognitive-state.yaml").write_text(
                "source:\n"
                "  commit: " + "b" * 40 + "\n"
                "maintenance:\n"
                "  last_run: shadow/run.md\n",
                encoding="utf-8",
            )
            with patch.object(prompt_context.projects, "ensure_shadow_repo",
                              return_value=shadow_dir), \
                    patch.object(prompt_context.projects, "get_project",
                                 return_value=project), \
                    patch.object(prompt_context.projects, "repo_dir",
                                 return_value=Path("C:/repos/7")), \
                    patch.object(prompt_context.projects, "current_branch",
                                 return_value="main"), \
                    patch.object(prompt_context.projects, "head_commit",
                                 return_value="c" * 40), \
                    patch.object(prompt_context.projects, "repo_dirty",
                                 return_value=False), \
                    patch.object(prompt_context.projects, "shadow_head",
                                 return_value="d" * 40), \
                    patch.object(prompt_context.projects, "shadow_dirty",
                                 return_value=False), \
                    patch.object(registry, "injectable_components", return_value=[]):
                context = prompt_context.build_prompt_context(
                    run_id=7,
                    project=project,
                    task_type="project-analysis",
                    task_mode="standard",
                    task_id=None,
                    trigger_kind="manual",
                    actor="tester",
                    started_at=1758412800,
                    harness=harness,
                    harness_name="dummy",
                    cwd="repo",
                    change=change,
                    ci_context={},
                    prompt_name="project-analysis",
                    prompt_version="1.1.0",
                    prompt_hash="sha256:" + "0" * 64,
                    run_dir=Path("C:/runs/7"),
                    report_file="C:/runs/7/report.md",
                    prompt_file="C:/runs/7/prompt.md",
                    report_delivery="输出完整 Markdown。",
                    change_policy="always",
                    extra="聚焦本次变更",
                )

        self.assertEqual(set(prompt_context.CONTEXT_FIELDS), set(context))
        self.assertEqual("1", context["context_schema_version"])
        self.assertEqual("7", context["run_id"])
        self.assertEqual("main", context["source_branch"])
        self.assertEqual("c" * 40, context["source_head_commit"])
        self.assertEqual("a" * 40, context["baseline_source_commit"])
        self.assertEqual("b" * 40, context["shadow_source_baseline_commit"])
        self.assertEqual("shadow/run.md", context["shadow_last_run_file"])
        self.assertEqual("", context["shadow_state_error"])

    def test_render_rejects_unknown_placeholder(self):
        rendered = prompt_context.render_prompt("run={{run_id}}", {"run_id": "7"})
        self.assertEqual("run=7", rendered)

        with self.assertRaisesRegex(RuntimeError, "missing_field"):
            prompt_context.render_prompt("{{missing_field}}", {"run_id": "7"})


if __name__ == "__main__":
    unittest.main()
