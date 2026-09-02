import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.exceptions import InvalidTag
from fastapi import HTTPException

from chronicler.app.config import Cfg
from chronicler.app.prompt_catalog import PromptCatalog, build_bundle
from chronicler.app.runtime import RuntimeProfile


class PromptCatalogTest(unittest.TestCase):
    def setUp(self):
        self.old_resource = Cfg.RESOURCE_DIR
        self.old_prompts = Cfg.PROMPTS_DIR
        self.old_data = Cfg.DATA

    def tearDown(self):
        Cfg.RESOURCE_DIR = self.old_resource
        Cfg.PROMPTS_DIR = self.old_prompts
        Cfg.DATA = self.old_data

    def test_source_catalog_exposes_structured_metadata_and_content(self):
        catalog = PromptCatalog()

        items = catalog.list()

        self.assertEqual(4, len(items))
        self.assertTrue(all(item.version == "1.0.0" for item in items))
        self.assertTrue(all(item.content_hash.startswith("sha256:") for item in items))
        self.assertTrue(all(catalog.content_for_display(item.name) for item in items))

    def test_sealed_bundle_discloses_only_metadata_and_accepts_visible_override(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            resources = root / "resources"
            Cfg.RESOURCE_DIR = resources
            Cfg.PROMPTS_DIR = self.old_prompts
            Cfg.DATA = root / "data"
            key = bytes(range(32))
            build_bundle(self.old_prompts, resources / "prompts.bundle", key)
            profile = RuntimeProfile("sealed", root, resources, root / "components",
                                     "metadata-only", False, key)
            with patch("chronicler.app.prompt_catalog.PROFILE", profile):
                catalog = PromptCatalog()
                item = catalog.resolve("project-analysis")
                self.assertEqual("1.0.0", item.version)
                self.assertIsNone(catalog.content_for_display(item.name))
                override = catalog.save_override(item.name, "1.0.1+customer", item.content)
                self.assertTrue(override.overridden)
                self.assertEqual(item.content, catalog.content_for_display(item.name))

    def test_content_change_requires_version_bump(self):
        catalog = PromptCatalog()
        item = catalog.resolve("project-analysis")
        with tempfile.TemporaryDirectory() as temp:
            Cfg.DATA = Path(temp)
            with self.assertRaises(HTTPException) as raised:
                catalog.save_override(item.name, item.version, item.content + "\nchanged")
            self.assertEqual(409, raised.exception.status_code)

    def test_source_catalog_migrates_legacy_markdown_override(self):
        builtin = PromptCatalog().resolve("project-analysis")
        with tempfile.TemporaryDirectory() as temp:
            Cfg.DATA = Path(temp)
            legacy = Cfg.prompts_override_dir() / "project-analysis.md"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(builtin.content, encoding="utf-8")

            migrated = PromptCatalog().resolve("project-analysis")

            self.assertEqual("0.0.0+legacy", migrated.version)
            self.assertTrue((Cfg.prompts_override_dir() / "project-analysis.yaml").is_file())
            self.assertTrue((Cfg.prompts_override_dir() / "project-analysis.md.migrated").is_file())

    def test_sealed_bundle_rejects_wrong_key(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            resources = root / "resources"
            Cfg.RESOURCE_DIR = resources
            Cfg.PROMPTS_DIR = self.old_prompts
            Cfg.DATA = root / "data"
            build_bundle(self.old_prompts, resources / "prompts.bundle", bytes(range(32)))
            profile = RuntimeProfile("sealed", root, resources, root / "components",
                                     "metadata-only", False, b"x" * 32)
            with patch("chronicler.app.prompt_catalog.PROFILE", profile):
                with self.assertRaises(InvalidTag):
                    PromptCatalog().list()


if __name__ == "__main__":
    unittest.main()