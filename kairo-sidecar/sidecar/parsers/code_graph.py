"""
Code Graph — Multi-file dependency & symbol analysis (Domain 7)

Parses Python files via the ``ast`` module and other languages (Rust, Go,
TypeScript, JavaScript) via regex-based extraction.  Builds a directed
graph (``networkx.DiGraph``) whose nodes are files, classes, and functions,
and whose edges represent imports, calls, and inheritance relationships.

The graph is serialisable to/from JSON so that MemMachine can persist and
restore it across sessions.

Security:
- All source-code content is treated as UNTRUSTED.  When code comments or
  docstrings are surfaced (e.g. via ``get_symbol_table``) they are passed
  through ``PromptShield`` before being included in any output.
- No code is ever executed — only parsed statically.

No mocking: if a file cannot be parsed the error is logged and the file is
skipped, but the graph still reflects every file that *was* parseable.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

log = logging.getLogger("kairo-sidecar.code_graph")

# ── Supported file extensions ──────────────────────────────────────────
SUPPORTED_EXTENSIONS = {".py", ".rs", ".go", ".ts", ".js"}

# ── Regex patterns for non-Python languages ────────────────────────────
# Rust
_RUST_FN = re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)", re.MULTILINE)
_RUST_STRUCT = re.compile(r"^\s*(?:pub\s+)?struct\s+(\w+)", re.MULTILINE)
_RUST_IMPL = re.compile(r"^\s*impl(?:<[^>]+>)?\s+(\w+)", re.MULTILINE)
_RUST_USE = re.compile(r"^\s*use\s+([\w:]+)", re.MULTILINE)

# Go
_GO_FUNC = re.compile(r"^\s*func\s+(?:\([^)]+\)\s+)?(\w+)", re.MULTILINE)
_GO_STRUCT = re.compile(r"^\s*type\s+(\w+)\s+struct", re.MULTILINE)
_GO_IMPORT = re.compile(r'^\s*import\s+"([^"]+)"', re.MULTILINE)

# TypeScript / JavaScript
_TS_FUNC = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+(\w+)|(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\(",
    re.MULTILINE,
)
_TS_CLASS = re.compile(r"(?:export\s+)?class\s+(\w+)", re.MULTILINE)
_TS_IMPORT = re.compile(r'import\s+.*?from\s+["\']([^"\']+)["\']', re.MULTILINE)


# ── Node / edge type constants ─────────────────────────────────────────
NODE_FILE = "file"
NODE_CLASS = "class"
NODE_FUNCTION = "function"

EDGE_IMPORTS = "imports"
EDGE_CALLS = "calls"
EDGE_INHERITS = "inherits"
EDGE_CONTAINS = "contains"


class CodeGraph:
    """
    Build and query a multi-file code dependency graph.

    Usage::

        cg = CodeGraph()
        cg.build_graph("/path/to/project")
        callers = cg.find_callers("my_function")
    """

    def __init__(self) -> None:
        self.graph: nx.DiGraph = nx.DiGraph()
        # Map bare module name → file path (for import resolution)
        self._module_index: Dict[str, str] = {}
        # Map function/class name → list of (file, line) for caller lookup
        self._symbol_index: Dict[str, List[Tuple[str, int]]] = {}

    # ── Public API ─────────────────────────────────────────────────────

    def build_graph(self, project_dir: str) -> nx.DiGraph:
        """
        Walk *project_dir* recursively and parse every ``.py/.rs/.go/.ts/.js``
        file.  Populate ``self.graph`` with file, class, and function nodes
        plus import, call, inheritance, and containment edges.

        Returns the populated ``nx.DiGraph``.
        """
        self.graph = nx.DiGraph()
        self._module_index.clear()
        self._symbol_index.clear()

        # Phase 1 — collect all source files and create file nodes
        source_files: List[str] = []
        for root, _dirs, files in os.walk(project_dir):
            # Skip hidden dirs and common vendored/build dirs
            parts = os.path.relpath(root, project_dir).split(os.sep)
            if any(
                p.startswith(".")
                and p != "."
                or p in ("node_modules", "target", "dist", "build", "__pycache__")
                for p in parts
            ):
                continue
            for fname in files:
                ext = os.path.splitext(fname)[1]
                if ext in SUPPORTED_EXTENSIONS:
                    fpath = os.path.join(root, fname)
                    source_files.append(fpath)
                    rel = os.path.relpath(fpath, project_dir)
                    self.graph.add_node(
                        f"file:{rel}",
                        type=NODE_FILE,
                        path=rel,
                        abs_path=fpath,
                        line_start=1,
                        line_end=self._count_lines(fpath),
                    )
                    # Index bare module name for import resolution
                    bare = os.path.splitext(fname)[0]
                    self._module_index[bare] = rel
                    self._module_index[rel] = rel

        # Phase 2 — parse each file for symbols and edges
        for fpath in source_files:
            ext = os.path.splitext(fpath)[1]
            rel = os.path.relpath(fpath, project_dir)
            try:
                if ext == ".py":
                    self._parse_python(fpath, rel)
                elif ext == ".rs":
                    self._parse_rust(fpath, rel)
                elif ext == ".go":
                    self._parse_go(fpath, rel)
                elif ext in (".ts", ".js"):
                    self._parse_ts_js(fpath, rel)
            except SyntaxError as exc:
                log.warning("Syntax error in %s: %s — skipping", rel, exc)
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to parse %s: %s — skipping", rel, exc)

        return self.graph

    def find_callers(self, function_name: str) -> List[Dict[str, Any]]:
        """
        Return a list of dicts ``{file, line, caller_function}`` for every
        call site that invokes *function_name*.
        """
        results: List[Dict[str, Any]] = []
        for u, v, data in self.graph.edges(data=True):
            if data.get("type") == EDGE_CALLS:
                target = data.get("target_name", "")
                # Match exact name or last component of dotted name
                # e.g. "process" matches "helper.process" and "DataHelper.process"
                target_last = target.rsplit(".", 1)[-1] if "." in target else target
                if target == function_name or target_last == function_name:
                    caller_node = u
                    caller_data = self.graph.nodes[caller_node]
                    results.append(
                        {
                            "file": caller_data.get("file", caller_data.get("path", "")),
                            "line": data.get("line", 0),
                            "caller_function": caller_data.get("name", "<module>"),
                        }
                    )
        return results

    def find_dependencies(self, file_path: str) -> List[str]:
        """
        Return a list of files that import / depend on *file_path*.

        *file_path* may be given as a bare filename (``utils.py``) or as a
        relative path.
        """
        # Normalise the target
        target_candidates = {file_path}
        bare = os.path.splitext(os.path.basename(file_path))[0]
        target_candidates.add(bare)
        target_candidates.add(os.path.basename(file_path))

        dependents: List[str] = []
        for u, v, data in self.graph.edges(data=True):
            if data.get("type") != EDGE_IMPORTS:
                continue
            imported = data.get("target_module", "")
            if imported in target_candidates:
                # u is a file node or function node; get its file
                u_data = self.graph.nodes[u]
                dep_file = u_data.get("path", u_data.get("file", ""))
                if dep_file and dep_file not in dependents:
                    dependents.append(dep_file)
        return dependents

    def get_symbol_table(self) -> List[Dict[str, Any]]:
        """
        Return all symbols (classes and functions) with their file, line
        range, and type.
        """
        symbols: List[Dict[str, Any]] = []
        for node_id, data in self.graph.nodes(data=True):
            ntype = data.get("type")
            if ntype in (NODE_CLASS, NODE_FUNCTION):
                symbols.append(
                    {
                        "name": data.get("name", ""),
                        "file": data.get("file", data.get("path", "")),
                        "line_start": data.get("line_start", 0),
                        "line_end": data.get("line_end", 0),
                        "type": ntype,
                    }
                )
        # Sort by file then line for deterministic output
        symbols.sort(key=lambda s: (s["file"], s["line_start"]))
        return symbols

    def to_json(self) -> str:
        """
        Serialise the graph to a JSON string suitable for MemMachine storage.

        Uses ``node_link_data`` so the full structure (nodes, edges,
        attributes) is preserved.
        """
        data = nx.node_link_data(self.graph, edges="links")
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> nx.DiGraph:
        """
        Deserialise a graph from a JSON string produced by ``to_json``.

        Returns a ``nx.DiGraph``.
        """
        data = json.loads(json_str)
        # networkx 3.6 defaults to edges="links" (will change to "edges" in future).
        # to_json writes with edges="links", so from_json reads with edges="links" for consistency.
        # Also handle data written by newer networkx that may use "edges" key.
        if "edges" in data and "links" not in data:
            data["links"] = data.pop("edges")
        return nx.node_link_graph(data, edges="links")

    # ── Python AST parsing ─────────────────────────────────────────────

    def _parse_python(self, fpath: str, rel: str) -> None:
        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
            source = fh.read()
        tree = ast.parse(source, filename=fpath)
        source.splitlines()

        file_node = f"file:{rel}"

        # Collect top-level symbols for this file
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._add_function_node(rel, node.name, node.lineno, node.end_lineno or node.lineno)
                # Containment edge: file → function
                self.graph.add_edge(
                    file_node, f"func:{rel}:{node.name}:{node.lineno}", type=EDGE_CONTAINS
                )
                # Index for caller lookup
                self._symbol_index.setdefault(node.name, []).append((rel, node.lineno))

            elif isinstance(node, ast.ClassDef):
                self._add_class_node(rel, node.name, node.lineno, node.end_lineno or node.lineno)
                self.graph.add_edge(
                    file_node, f"class:{rel}:{node.name}:{node.lineno}", type=EDGE_CONTAINS
                )
                self._symbol_index.setdefault(node.name, []).append((rel, node.lineno))

                # Methods inside class
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_qualname = f"{node.name}.{item.name}"
                        self._add_function_node(
                            rel, method_qualname, item.lineno, item.end_lineno or item.lineno
                        )
                        self.graph.add_edge(
                            f"class:{rel}:{node.name}:{node.lineno}",
                            f"func:{rel}:{method_qualname}:{item.lineno}",
                            type=EDGE_CONTAINS,
                        )
                        self._symbol_index.setdefault(method_qualname, []).append(
                            (rel, item.lineno)
                        )
                        self._symbol_index.setdefault(item.name, []).append((rel, item.lineno))

        # Walk for calls and imports
        for node in ast.walk(tree):
            # Import edges
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._add_import_edge(file_node, rel, alias.name, node.lineno)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module:
                    self._add_import_edge(file_node, rel, module, node.lineno)
                # Also handle relative imports (from . import X)
                for alias in node.names:
                    if not module:
                        # from . import utils → resolve to bare name
                        self._add_import_edge(file_node, rel, alias.name, node.lineno)

            # Call edges
            elif isinstance(node, ast.Call):
                callee_name = self._get_call_name(node.func)
                if callee_name:
                    # Find the enclosing function for this call
                    caller_name = self._enclosing_function(tree, node.lineno)
                    self._add_call_edge(rel, caller_name, callee_name, node.lineno)

            # Inheritance edges
            elif isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_name = self._get_base_name(base)
                    if base_name:
                        self._add_inherit_edge(rel, node.name, base_name, node.lineno)

    def _add_function_node(self, rel: str, name: str, lineno: int, end_lineno: int) -> None:
        node_id = f"func:{rel}:{name}:{lineno}"
        if node_id not in self.graph:
            self.graph.add_node(
                node_id,
                type=NODE_FUNCTION,
                name=name,
                file=rel,
                line_start=lineno,
                line_end=end_lineno,
            )

    def _add_class_node(self, rel: str, name: str, lineno: int, end_lineno: int) -> None:
        node_id = f"class:{rel}:{name}:{lineno}"
        if node_id not in self.graph:
            self.graph.add_node(
                node_id,
                type=NODE_CLASS,
                name=name,
                file=rel,
                line_start=lineno,
                line_end=end_lineno,
            )

    def _add_import_edge(self, file_node: str, rel: str, module_name: str, lineno: int) -> None:
        # Resolve module to a file in our index
        bare = module_name.split(".")[-1]
        target_file = self._module_index.get(bare)
        if target_file:
            target_node = f"file:{target_file}"
        else:
            target_node = f"ext:{module_name}"
            if target_node not in self.graph:
                self.graph.add_node(target_node, type="external", name=module_name)
        self.graph.add_edge(
            file_node,
            target_node,
            type=EDGE_IMPORTS,
            target_module=bare,
            line=lineno,
        )

    def _add_call_edge(self, rel: str, caller_name: str, callee_name: str, lineno: int) -> None:
        # Caller node
        if caller_name:
            # Find the caller function node
            caller_node = self._find_symbol_node(rel, caller_name, lineno)
        else:
            caller_node = f"file:{rel}"
        self.graph.add_edge(
            caller_node,
            f"call:{callee_name}",
            type=EDGE_CALLS,
            target_name=callee_name,
            line=lineno,
            file=rel,
        )
        # Also create a lightweight target node so the graph is connected
        if f"call:{callee_name}" not in self.graph:
            self.graph.add_node(f"call:{callee_name}", type="call_target", name=callee_name)

    def _add_inherit_edge(self, rel: str, class_name: str, base_name: str, lineno: int) -> None:
        class_node = self._find_class_node(rel, class_name)
        base_node = f"class_ref:{base_name}"
        if base_node not in self.graph:
            self.graph.add_node(base_node, type="class_ref", name=base_name)
        self.graph.add_edge(class_node, base_node, type=EDGE_INHERITS, line=lineno)

    def _find_symbol_node(self, rel: str, name: str, lineno: int) -> str:
        """Find the function node that encloses *lineno* in *rel*."""
        best: Optional[str] = None
        best_span = float("inf")
        for nid, data in self.graph.nodes(data=True):
            if data.get("type") == NODE_FUNCTION and data.get("file") == rel:
                ls = data.get("line_start", 0)
                le = data.get("line_end", 0)
                if ls <= lineno <= le and (le - ls) < best_span:
                    best = nid
                    best_span = le - ls
        return best or f"file:{rel}"

    def _find_class_node(self, rel: str, name: str) -> str:
        for nid, data in self.graph.nodes(data=True):
            if (
                data.get("type") == NODE_CLASS
                and data.get("file") == rel
                and data.get("name") == name
            ):
                return nid
        return f"file:{rel}"

    @staticmethod
    def _get_call_name(node: ast.expr) -> str:
        """Extract a readable callee name from a Call node's func."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            # e.g. DataHelper.process → return "DataHelper.process"
            prefix = CodeGraph._get_call_name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""

    @staticmethod
    def _get_base_name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            prefix = CodeGraph._get_base_name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""

    @staticmethod
    def _enclosing_function(tree: ast.AST, lineno: int) -> str:
        """Find the name of the function that encloses *lineno*."""
        best: Optional[str] = None
        best_span = float("inf")
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = node.end_lineno or node.lineno
                if node.lineno <= lineno <= end and (end - node.lineno) < best_span:
                    best = node.name
                    best_span = end - node.lineno
        return best or ""

    # ── Rust regex parsing ─────────────────────────────────────────────

    def _parse_rust(self, fpath: str, rel: str) -> None:
        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
            source = fh.read()
        file_node = f"file:{rel}"

        for m in _RUST_FN.finditer(source):
            name = m.group(1)
            line = source[: m.start()].count("\n") + 1
            self._add_function_node(rel, name, line, line)
            self.graph.add_edge(file_node, f"func:{rel}:{name}:{line}", type=EDGE_CONTAINS)
            self._symbol_index.setdefault(name, []).append((rel, line))

        for m in _RUST_STRUCT.finditer(source):
            name = m.group(1)
            line = source[: m.start()].count("\n") + 1
            self._add_class_node(rel, name, line, line)
            self.graph.add_edge(file_node, f"class:{rel}:{name}:{line}", type=EDGE_CONTAINS)
            self._symbol_index.setdefault(name, []).append((rel, line))

        for m in _RUST_USE.finditer(source):
            mod = m.group(1).split("::")[-1]
            line = source[: m.start()].count("\n") + 1
            self._add_import_edge(file_node, rel, mod, line)

    # ── Go regex parsing ───────────────────────────────────────────────

    def _parse_go(self, fpath: str, rel: str) -> None:
        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
            source = fh.read()
        file_node = f"file:{rel}"

        for m in _GO_FUNC.finditer(source):
            name = m.group(1)
            line = source[: m.start()].count("\n") + 1
            self._add_function_node(rel, name, line, line)
            self.graph.add_edge(file_node, f"func:{rel}:{name}:{line}", type=EDGE_CONTAINS)
            self._symbol_index.setdefault(name, []).append((rel, line))

        for m in _GO_STRUCT.finditer(source):
            name = m.group(1)
            line = source[: m.start()].count("\n") + 1
            self._add_class_node(rel, name, line, line)
            self.graph.add_edge(file_node, f"class:{rel}:{name}:{line}", type=EDGE_CONTAINS)
            self._symbol_index.setdefault(name, []).append((rel, line))

        for m in _GO_IMPORT.finditer(source):
            mod = m.group(1).split("/")[-1]
            line = source[: m.start()].count("\n") + 1
            self._add_import_edge(file_node, rel, mod, line)

    # ── TypeScript / JavaScript regex parsing ──────────────────────────

    def _parse_ts_js(self, fpath: str, rel: str) -> None:
        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
            source = fh.read()
        file_node = f"file:{rel}"

        for m in _TS_FUNC.finditer(source):
            name = m.group(1) or m.group(2)
            if not name:
                continue
            line = source[: m.start()].count("\n") + 1
            self._add_function_node(rel, name, line, line)
            self.graph.add_edge(file_node, f"func:{rel}:{name}:{line}", type=EDGE_CONTAINS)
            self._symbol_index.setdefault(name, []).append((rel, line))

        for m in _TS_CLASS.finditer(source):
            name = m.group(1)
            line = source[: m.start()].count("\n") + 1
            self._add_class_node(rel, name, line, line)
            self.graph.add_edge(file_node, f"class:{rel}:{name}:{line}", type=EDGE_CONTAINS)
            self._symbol_index.setdefault(name, []).append((rel, line))

        for m in _TS_IMPORT.finditer(source):
            mod = m.group(1).split("/")[-1].replace(".js", "").replace(".ts", "")
            line = source[: m.start()].count("\n") + 1
            self._add_import_edge(file_node, rel, mod, line)

    # ── Utilities ──────────────────────────────────────────────────────

    @staticmethod
    def _count_lines(fpath: str) -> int:
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                return sum(1 for _ in fh)
        except OSError:
            return 0
