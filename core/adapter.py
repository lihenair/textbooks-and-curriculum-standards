"""适配器四件套。缺任何一件即非零退出，不降级继续。"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml


REQUIRED_TEMPLATES = (
    "canon-line.txt",
    "chapter-graph.md",
    "study-page.md",
    "graph-seeds.py",
    "skill-snippet.md",
)


@dataclass
class Adapter:
    name: str
    root: Path
    config: dict
    templates: dict[str, str]
    checks: object

    @property
    def target_yaml(self) -> Path:
        return self.root / "target.yaml"


def load_adapter(pipeline_root: Path, name: str) -> Adapter:
    root = Path(pipeline_root) / "targets" / name
    required = [
        root / "target.yaml",
        root / "checks.py",
        root / "prompts" / "draft-chapter.md",
        *[(root / "templates" / item) for item in REQUIRED_TEMPLATES],
    ]
    missing = [str(path.relative_to(pipeline_root)) for path in required if not path.is_file()]
    if missing:
        joined = "、".join(missing)
        print(f"适配器不完整，拒绝继续：{joined}", file=sys.stderr)
        raise SystemExit(2)
    config = yaml.safe_load((root / "target.yaml").read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        print("target.yaml 顶层必须是映射", file=sys.stderr)
        raise SystemExit(2)
    for key in ("repo", "ref", "skill_dir", "paths", "seeds"):
        if key not in config:
            print(f"target.yaml 缺少 {key}", file=sys.stderr)
            raise SystemExit(2)
    templates = {
        item: (root / "templates" / item).read_text(encoding="utf-8")
        for item in REQUIRED_TEMPLATES
    }
    checks = _load_checks(root / "checks.py")
    if not callable(getattr(checks, "check", None)):
        print("checks.py 必须提供 check(ir, artifacts)", file=sys.stderr)
        raise SystemExit(2)
    return Adapter(name=name, root=root, config=config, templates=templates, checks=checks)


def _load_checks(path: Path):
    spec = importlib.util.spec_from_file_location(f"target_checks_{path.parent.name}", path)
    if spec is None or spec.loader is None:
        print(f"无法加载 {path}", file=sys.stderr)
        raise SystemExit(2)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve(config: dict, token: str, repo: Path) -> Path:
    skill = Path(repo) / str(config["skill_dir"])
    if token.startswith("{repo}/"):
        return Path(repo) / token[len("{repo}/") :]
    if token.startswith("{skill}/"):
        return skill / token[len("{skill}/") :]
    raise SystemExit(2)


def path_map(adapter: Adapter, repo: Path) -> dict[str, Path]:
    mapped = {}
    for key, token in adapter.config["paths"].items():
        mapped[key] = resolve(adapter.config, str(token), repo)
    return mapped
