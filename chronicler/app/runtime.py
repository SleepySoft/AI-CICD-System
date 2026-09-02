"""运行时发行 Profile 与资源路径（source/sealed，构建时固化）。"""
import base64
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeProfile:
    name: str
    install_root: Path
    resource_root: Path
    components_root: Path
    prompt_disclosure: str
    persist_rendered_prompt: bool
    prompt_key: bytes | None = None

    @property
    def static_root(self) -> Path:
        return (self.resource_root / "app" / "static" if self.name == "source"
                else self.resource_root / "static")

    @property
    def sealed(self) -> bool:
        return self.name == "sealed"


def _source_profile() -> RuntimeProfile:
    package_root = Path(__file__).resolve().parent.parent
    return RuntimeProfile(
        name="source",
        install_root=package_root.parent,
        resource_root=package_root,
        components_root=package_root / "components",
        prompt_disclosure="full",
        persist_rendered_prompt=True,
    )


def _load_profile() -> RuntimeProfile:
    try:
        from ._sealed_profile import PROMPT_KEY_B64  # type: ignore[import-not-found]
    except ImportError:
        return _source_profile()
    try:
        install_root = Path(__compiled__.containing_dir)  # type: ignore[name-defined]  # Nuitka
    except NameError:
        install_root = Path(sys.argv[0]).resolve().parent
    return RuntimeProfile(
        name="sealed",
        install_root=install_root,
        resource_root=install_root / "resources",
        components_root=install_root / "components",
        prompt_disclosure="metadata-only",
        persist_rendered_prompt=False,
        prompt_key=base64.urlsafe_b64decode(PROMPT_KEY_B64),
    )


PROFILE = _load_profile()


def component_python() -> str:
    """外置组件 Python hook 的解释器；sealed 核心不把组件代码编入自身。"""
    if not PROFILE.sealed:
        return sys.executable
    command = os.environ.get("CHRONICLER_COMPONENT_PYTHON",
                             "python" if sys.platform == "win32" else "python3")
    if not shutil.which(command):
        raise RuntimeError(f"外置组件 Python 解释器不可用：{command}（设置 CHRONICLER_COMPONENT_PYTHON）")
    return command
