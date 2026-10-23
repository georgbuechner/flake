"""Load the real route functions without running production startup code."""
import ast
from pathlib import Path

from flask_login import LoginManager

ROOT = Path(__file__).resolve().parents[1]


def load_routes(app, names=None, *, decorated=False):
    source = ROOT / "src/app.py"
    nodes = []
    for node in ast.parse(source.read_text()).body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and (names is None or node.name in names):
            if not decorated:
                node.decorator_list = []
            nodes.append(node)
    namespace = {
        "app": app, "login_manager": LoginManager(app),
        "SIGNATURE_PATH": str(ROOT / "src/signatures"),
        "OVERVIEW_BATCH_SIZE": 50, "LAB_PASSWORD": "test-only", "generation_threads": {},
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)
    namespace["register_error_handlers"](app)
    return namespace
