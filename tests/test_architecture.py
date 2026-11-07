"""core의 정적 의존 경계와 직접 파일 입출력을 검사한다."""

import ast
from importlib.util import resolve_name
from pathlib import Path
import sys

import pytest

CORE = Path(__file__).resolve().parents[1] / "src/frame/core"
BANNED = ("frame.adapters", "frame.cli", "frame.config_loader", "subprocess", "urllib", "socket")


def violations(source, module="frame.core.example"):
    tree = ast.parse(source)
    errors = []
    aliases = {}
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
                aliases[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = resolve_name("." * node.level + base, module.rpartition(".")[0])
            names.append(base)
            for alias in node.names:
                full = f"{base}.{alias.name}"
                names.append(full)
                aliases[alias.asname or alias.name] = full
        for name in names:
            if any(name == banned or name.startswith(banned + ".") for banned in BANNED):
                errors.append(f"{node.lineno}: 금지된 의존 {name}")
            if name.split(".")[0] not in sys.stdlib_module_names | {"frame", "__future__"}:
                errors.append(f"{node.lineno}: 표준 라이브러리 외 의존 {name}")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            name = aliases.get(func.id, func.id)
            if name == "open" or name.endswith(".open") or name in ("__import__", "eval", "exec"):
                errors.append(f"{node.lineno}: 입출력 또는 동적 실행 {name}")
        elif isinstance(func, ast.Attribute) and func.attr in (
                "open", "read_text", "read_bytes", "write_text", "write_bytes", "import_module"):
            errors.append(f"{node.lineno}: 파일 입출력 또는 동적 가져오기 {func.attr}")
    return errors


@pytest.mark.parametrize("path", sorted(CORE.rglob("*.py")), ids=lambda p: p.name)
def test_core_is_pure(path):
    module = "frame.core." + path.relative_to(CORE).with_suffix("").as_posix().replace("/", ".")
    assert not violations(path.read_text(encoding="utf-8"), module)


@pytest.mark.parametrize("source", [
    "import frame.adapters.claude_cli", "from frame import cli", "from .. import adapters",
    "import subprocess as process", "from urllib.request import urlopen", "import socket",
    "open('문서')", "from builtins import open as read\nread('문서')",
    "from pathlib import Path\nPath('문서').read_text()", "import requests",
])
def test_guard_detects_forbidden_examples(source):
    assert violations(source)
