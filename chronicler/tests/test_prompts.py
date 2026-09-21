import asyncio
import tempfile
import unittest
from pathlib import Path
import time
import re

from fastapi import HTTPException

from chronicler.app import db, projects, registry, runner, tasks
from chronicler.app.config import Cfg
from chronicler.app.routers import config
from chronicler.app.prompt_context import CONTEXT_FIELDS, render_prompt


class PromptRegistryTest(unittest.TestCase):
    def test_two_tasks_map_to_two_formal_prompts(self):
        task_types = registry.list_task_types()

        self.assertEqual(2, len(task_types))
        self.assertEqual(2, len({item["prompt"] for item in task_types}))
        self.assertEqual([item["name"] for item in task_types], tasks.PRESET_TASKS)
        self.assertEqual("operational_reporter", registry.get_task_type("operational_reporter")["prompt"])
        self.assertEqual("comprehensive", registry.get_task_type("operational_reporter")["mode"])
        self.assertEqual("project_cognitive_maintainer",
                         registry.get_task_type("project_cognitive_maintainer")["prompt"])
        self.assertEqual("incremental",
                         registry.get_task_type("project_cognitive_maintainer")["mode"])

    def test_legacy_task_types_are_rejected(self):
        """旧任务类型不再映射；历史 Run 仍可只读展示，但不能触发。"""
        for task_type in ("code-insight", "deviation-analysis", "compliance-check",
                          "structured-docs", "knowhow-distill", "project-analysis",
                          "documentation-update", "daily-report", "comprehensive-report",
                          "knowledge-capture"):
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

        self.assertEqual(2, len(task_types))
        self.assertEqual(2, len(prompts))
        self.assertTrue(all("prompt" in item and "mode" in item for item in task_types))
        self.assertEqual({"project_cognitive_maintainer", "operational_reporter"},
                         {item["name"] for item in prompts})

    def test_operational_reporter_prompt_renders_required_context(self):
        context = {key: f"[{key}]" for key in CONTEXT_FIELDS}
        context.update({
            "extra": "关注本周失败构建",
            "report_file": "C:/runs/7/report.md",
            "prompt_file": "C:/runs/7/prompt.md",
            "source_head_commit": "target456",
            "report_delivery": "输出完整 Markdown。",
            "change_context": "- 状态：有增量",
            "baseline_source_commit": "base123",
            "task_period_start": "2026-09-14",
            "task_period_end": "2026-09-20",
            "harness_report_mode": "daily",
        })

        template, _ = registry.load_prompt("operational_reporter")
        rendered = render_prompt(template, context)

        self.assertIsNone(re.search(r"\{\{[a-z_]+\}\}", rendered))
        self.assertIn("base123", rendered)
        self.assertIn("target456", rendered)

    def test_all_new_task_prompts_render_without_unknown_placeholders(self):
        context = {key: f"[{key}]" for key in CONTEXT_FIELDS}
        context.update({
            "extra": "聚焦最近一次变更",
            "report_file": "C:/runs/7/report.md",
            "prompt_file": "C:/runs/7/prompt.md",
            "source_head_commit": "abc123",
            "report_delivery": "输出完整 Markdown。",
            "change_context": "- 状态：有增量",
        })

        for task_type in tasks.PRESET_TASKS:
            with self.subTest(task_type=task_type):
                template, _, spec = registry.load_task_prompt(task_type)
                rendered = render_prompt(template, {**context, "task_mode": spec["mode"]})
                self.assertIsNone(re.search(r"\{\{[a-z_]+\}\}", rendered))
                self.assertIn(context["report_file"], rendered)

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


class PromptTaskMigrationTest(unittest.TestCase):
    def test_backfill_replaces_legacy_tasks_and_preserves_history(self):
        old_paths = Cfg.DATA, Cfg.PUBLIC, Cfg.WORKSPACE
        old_connection = getattr(db._local, "conn", None)
        with tempfile.TemporaryDirectory() as temp:
            try:
                Cfg.DATA = Path(temp) / "data"
                Cfg.PUBLIC = Path(temp) / "public"
                Cfg.WORKSPACE = Path(temp) / "workspace"
                db._local.conn = None
                db.init()
                project = projects.create_project("legacy", "https://example.invalid/repo.git")
                old_task_id = db.execute(
                    "INSERT INTO task_defs(project_id, name, task_type, created_at)"
                    " VALUES (?,?,?,strftime('%s','now'))",
                    (project["id"], "旧任务", "project-analysis"))
                custom_task_id = db.execute(
                    "INSERT INTO task_defs(project_id, name, task_type, prompt_override, created_at)"
                    " VALUES (?,?,?,?,strftime('%s','now'))",
                    (project["id"], "自定义任务", "custom", "# 自定义 Prompt"))
                run_id = db.execute(
                    "INSERT INTO task_runs(project_id, task_id, task_type, status, trigger,"
                    " harness, prompt_version, input_snapshot, artifacts, publication,"
                    " created_by, started_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (project["id"], old_task_id, "project-analysis", "success", "manual",
                     "dummy", "1.1.0", "not-json", "not-json", "not-json",
                     "test", time.time()))

                tasks.backfill_preset_tasks()

                self.assertIsNone(runner.get_run(run_id)["task_id"])
                historical = runner.get_run(run_id)
                self.assertEqual({}, historical["input_snapshot"])
                self.assertEqual([], historical["artifacts"])
                self.assertEqual({}, historical["publication"])
                task_types = {item["task_type"] for item in tasks.list_tasks(project["id"])}
                self.assertEqual({"custom", *tasks.PRESET_TASKS}, task_types)
                self.assertNotIn("project-analysis", task_types)
                self.assertTrue(tasks.get_task(custom_task_id)["prompt_override"])
            finally:
                current = getattr(db._local, "conn", None)
                if current is not None:
                    current.close()
                db._local.conn = old_connection
                Cfg.DATA, Cfg.PUBLIC, Cfg.WORKSPACE = old_paths


if __name__ == "__main__":
    unittest.main()
