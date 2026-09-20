import re
import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from chronicler.app import registry, runner, tasks
from chronicler.app.routers import config


class PromptRegistryTest(unittest.TestCase):
    def test_five_tasks_share_four_prompt_families(self):
        task_types = registry.list_task_types()

        self.assertEqual(5, len(task_types))
        self.assertEqual(4, len({item["prompt"] for item in task_types}))
        self.assertEqual([item["name"] for item in task_types], tasks.PRESET_TASKS)
        self.assertEqual("periodic-report", registry.get_task_type("daily-report")["prompt"])
        self.assertEqual("daily", registry.get_task_type("daily-report")["mode"])
        self.assertEqual("comprehensive", registry.get_task_type("comprehensive-report")["mode"])

    def test_legacy_task_types_are_rejected(self):
        """旧任务类型的兼容映射已按计划清理（ADR-0034 后果项）：直接拒绝。"""
        for task_type in ("code-insight", "deviation-analysis", "compliance-check",
                          "structured-docs", "knowhow-distill"):
            with self.subTest(task_type=task_type):
                with self.assertRaises(HTTPException) as raised:
                    registry.load_task_prompt(task_type)
                self.assertEqual(404, raised.exception.status_code)

    def test_custom_task_requires_its_own_prompt(self):
        self.assertEqual("custom", registry.get_task_type("custom")["mode"])
        with self.assertRaises(HTTPException) as raised:
            registry.load_task_prompt("custom")
        self.assertEqual(422, raised.exception.status_code)

    def test_config_api_separates_task_types_from_prompt_families(self):
        task_types = asyncio.run(config.task_types({"username": "test"}))
        prompts = asyncio.run(config.prompts({"username": "test"}))

        self.assertEqual(5, len(task_types))
        self.assertEqual(6, len(prompts))
        self.assertTrue(all("prompt" in item and "mode" in item for item in task_types))
        self.assertEqual({"documentation-update", "knowledge-capture",
                          "periodic-report", "project-analysis",
                          "project_cognitive_maintainer", "operational_reporter"},
                         {item["name"] for item in prompts})

    def test_operational_reporter_prompt_renders_required_context(self):
        project = {"id": 7, "name": "sample"}
        values = {
            "extra": "关注本周失败构建",
            "report_file": "C:/runs/7/report.md",
            "prompt_file": "C:/runs/7/prompt.md",
            "repo_head": "abc123",
            "ci_context": "{}",
            "report_delivery": "输出完整 Markdown。",
            "change_context": "- 状态：有增量",
            "baseline_commit": "base123",
            "target_commit": "target456",
            "period_start": "2026-09-14",
            "period_end": "2026-09-20",
            "report_mode": "daily",
        }

        with patch.object(runner.projects, "repo_dir", return_value=Path("C:/repos/7")), \
                patch.object(runner.projects, "ensure_shadow_repo", return_value=Path("C:/shadow/7")), \
                patch.object(registry, "injectable_components", return_value=[]):
            template, _ = registry.load_prompt("operational_reporter")
            rendered = runner._render_prompt(template, project, values)

        self.assertIsNone(re.search(r"\{\{[a-z_]+\}\}", rendered))
        self.assertIn(values["baseline_commit"], rendered)
        self.assertIn(values["target_commit"], rendered)

    def test_all_new_task_prompts_render_without_unknown_placeholders(self):
        project = {"id": 7, "name": "sample"}
        values = {
            "extra": "聚焦最近一次变更",
            "report_file": "C:/runs/7/report.md",
            "prompt_file": "C:/runs/7/prompt.md",
            "repo_head": "abc123",
            "ci_context": "{}",
            "report_delivery": "输出完整 Markdown。",
            "change_context": "- 状态：有增量",
        }

        with patch.object(runner.projects, "repo_dir", return_value=Path("C:/repos/7")), \
                patch.object(runner.projects, "ensure_shadow_repo", return_value=Path("C:/shadow/7")), \
                patch.object(registry, "injectable_components", return_value=[]):
            for task_type in tasks.PRESET_TASKS:
                with self.subTest(task_type=task_type):
                    template, _, spec = registry.load_task_prompt(task_type)
                    rendered = runner._render_prompt(template, project,
                                                     {**values, "task_mode": spec["mode"]})
                    self.assertIsNone(re.search(r"\{\{[a-z_]+\}\}", rendered))
                    self.assertIn(values["report_file"], rendered)

    def test_report_delivery_matches_harness_contract(self):
        report_file = "C:/runs/7/report.md"
        stdout = runner._report_delivery({"report_mode": "stdout"}, report_file)
        automatic = runner._report_delivery(
            {"report_mode": "file", "command_template": "agent -o {report_file}"}, report_file)
        explicit = runner._report_delivery(
            {"report_mode": "file", "command_template": "agent --prompt {prompt_file}"}, report_file)

        self.assertIn("stdout", stdout)
        self.assertIn("自动", automatic)
        self.assertIn(report_file, explicit)


if __name__ == "__main__":
    unittest.main()
