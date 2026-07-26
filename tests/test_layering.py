"""レイヤの依存方向を機械的に検証する（docs/spec/02-architecture.md §2）。

依存は interface → services → adapters → domain の一方向のみ。
domain は外部ライブラリにも依存しない。
"""

import ast
from pathlib import Path

import pytest

import priconne_cb_collector

PACKAGE_ROOT = Path(priconne_cb_collector.__file__).parent
PACKAGE = "priconne_cb_collector"

# 各層が import してよい層（自分自身とパッケージ直下のモジュールは常に可）
ALLOWED = {
    "domain": set(),
    "adapters": {"domain"},
    "services": {"domain", "adapters"},
    "interface": {"domain", "adapters", "services"},
}

# domain が触れてはいけない外部ライブラリ
FORBIDDEN_IN_DOMAIN = {"httpx", "discord", "sqlite3", "yaml", "dotenv"}


def iter_modules():
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        rel = path.relative_to(PACKAGE_ROOT)
        layer = rel.parts[0] if len(rel.parts) > 1 else None
        yield path, layer, rel


def imported_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


LAYERED = [(p, layer, rel) for p, layer, rel in iter_modules() if layer in ALLOWED]


@pytest.mark.parametrize(("path", "layer", "rel"), LAYERED, ids=[str(rel) for _, _, rel in LAYERED])
def test_layer_only_imports_downward(path, layer, rel):
    for name in imported_names(path):
        if not name.startswith(f"{PACKAGE}."):
            continue
        parts = name.split(".")
        target = parts[1]
        if target == layer or target not in ALLOWED:
            continue  # 同一層、またはパッケージ直下のモジュール
        assert target in ALLOWED[layer], (
            f"{rel} ({layer} 層) が {target} 層を import している: {name}"
        )


DOMAIN = [(p, rel) for p, layer, rel in iter_modules() if layer == "domain"]


@pytest.mark.parametrize(("path", "rel"), DOMAIN, ids=[str(rel) for _, rel in DOMAIN])
def test_domain_has_no_external_dependencies(path, rel):
    for name in imported_names(path):
        root = name.split(".")[0]
        assert root not in FORBIDDEN_IN_DOMAIN, f"{rel} は domain 層なので {root} に依存できない"


def test_every_layer_is_covered():
    """レイヤ追加時にこのテストの更新漏れを検知する。"""
    found = {rel.parts[0] for _, _, rel in iter_modules() if rel.parts[0] in ALLOWED}
    assert found == set(ALLOWED)
