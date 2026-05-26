import os
import re
from pathlib import Path

IMPORT_PATTERNS = {
    ".py": [
        r"^\s*import\s+([\w.]+)",
        r"^\s*from\s+([\w.]+)\s+import",
    ],
    ".js": [
        r"""from\s+['"]((?:\.{1,2}/|@/|~/)[^'"]+)['"]""",
        r"""require\s*\(\s*['"](.*?)['"]\s*\)""",
        r"""import\s*\(\s*['"]((?:\.{1,2}/|@/|~/)[^'"]+)['"]\s*\)""",
    ],
    ".ts": [
        r"""from\s+['"]((?:\.{1,2}/|@/|~/)[^'"]+)['"]""",
        r"""require\s*\(\s*['"](.*?)['"]\s*\)""",
        r"""import\s*\(\s*['"]((?:\.{1,2}/|@/|~/)[^'"]+)['"]\s*\)""",
    ],
    ".jsx": [
        r"""from\s+['"]((?:\.{1,2}/|@/|~/)[^'"]+)['"]""",
        r"""require\s*\(\s*['"](.*?)['"]\s*\)""",
    ],
    ".tsx": [
        r"""from\s+['"]((?:\.{1,2}/|@/|~/)[^'"]+)['"]""",
        r"""require\s*\(\s*['"](.*?)['"]\s*\)""",
    ],
    ".vue": [
        r"""from\s+['"]([\w./\-@~]+)['"]""",
        r"""import\s*\(\s*['"]([\w./\-@~]+)['"]\s*\)""",
        r"""require\s*\(\s*['"](.*?)['"]\s*\)""",
    ],
    ".java": [r"^\s*import\s+([\w.]+);"],
    ".cs": [r"^\s*using\s+([\w.]+);"],
    ".go": [r'"([\w./\-]+)"'],
    ".php": [
        r"""(?:require|include)(?:_once)?\s*['"](.*?)['"]""",
        r"^\s*use\s+([\w\\]+)",
    ],
    ".html": [
        r"""<script[^>]+src=['"]([^'"]+)['"]""",           # <script src="./app.js">
        r"""<link[^>]+href=['"]([^'"]+)['"]""",            # <link href="./style.css">
        r"""\{%-?\s*include\s+['"]([^'"]+)['"]""",         # Jinja2/Django {% include 'file.html' %}
        r"""<%[-=]?\s*include\s*\(['"]([^'"]+)['"]""",     # EJS <%- include('./partial') %>
    ],
    ".htm": [
        r"""<script[^>]+src=['"]([^'"]+)['"]""",
        r"""<link[^>]+href=['"]([^'"]+)['"]""",
        r"""\{%-?\s*include\s+['"]([^'"]+)['"]""",
        r"""<%[-=]?\s*include\s*\(['"]([^'"]+)['"]""",
    ],
}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "target", "bin", "obj", ".idea", ".vs",
}

TEST_DIRS = {"tests", "test", "__tests__", "spec", "specs"}
TEST_NAME_PATTERNS = ["test_", "_test", ".spec.", ".test.", "_spec"]

MAX_FILES_TO_SCAN = 1000
MAX_FILE_SIZE = 200 * 1024
MAX_RELATED_FILES = 12
MAX_RELATED_CONTENT = 25000
MAX_TEST_FILES = 5
MAX_TEST_CONTENT = 25000

# Layer 2: symbol grep — extract exported names per language
EXPORT_PATTERNS = {
    ".js":   re.compile(r"export\s+(?:default\s+)?(?:const|function|async\s+function|class|type|interface)\s+(\w+)"),
    ".ts":   re.compile(r"export\s+(?:default\s+)?(?:const|function|async\s+function|class|type|interface)\s+(\w+)"),
    ".jsx":  re.compile(r"export\s+(?:default\s+)?(?:const|function|async\s+function|class)\s+(\w+)"),
    ".tsx":  re.compile(r"export\s+(?:default\s+)?(?:const|function|async\s+function|class|type|interface)\s+(\w+)"),
    ".vue":  re.compile(r"export\s+(?:default\s+)?(?:const|function|async\s+function|class)\s+(\w+)"),
    ".py":   re.compile(r"^(?:def|class)\s+([A-Za-z][A-Za-z0-9_]*)", re.MULTILINE),
    ".java": re.compile(r"public\s+(?:(?:abstract|final|static)\s+)*(?:class|interface|enum|record)\s+(\w+)"),
    ".cs":   re.compile(r"(?:public|internal|protected)\s+(?:(?:abstract|static|sealed|partial)\s+)*(?:class|interface|enum|record|struct)\s+(\w+)"),
    ".go":   re.compile(r"^(?:func|type)\s+([A-Z][A-Za-z0-9_]*)", re.MULTILINE),
    ".php":  re.compile(r"^(?:function|class|interface|trait)\s+(\w+)", re.MULTILINE),
}

# Chỉ grep trong file cùng nhóm ngôn ngữ để tránh false positive cross-language
SAME_LANG_EXTS = {
    ".js":   {".js", ".ts", ".vue", ".jsx", ".tsx"},
    ".ts":   {".js", ".ts", ".vue", ".jsx", ".tsx"},
    ".jsx":  {".js", ".ts", ".vue", ".jsx", ".tsx"},
    ".tsx":  {".js", ".ts", ".vue", ".jsx", ".tsx"},
    ".vue":  {".js", ".ts", ".vue", ".jsx", ".tsx"},
    ".py":   {".py"},
    ".java": {".java"},
    ".cs":   {".cs"},
    ".go":   {".go"},
    ".php":  {".php"},
}

MIN_SYMBOL_LEN = 4

_graph_cache: dict = {}


def _get_graph(project_root: str) -> dict:
    if project_root not in _graph_cache:
        _graph_cache[project_root] = _build_import_graph(project_root)
    return _graph_cache[project_root]


GENERIC_SYMBOLS = {
    "main", "init", "run", "get", "set", "save", "load", "create", "update",
    "delete", "handle", "process", "execute", "start", "stop", "index",
    "test", "setup", "helper", "base", "default", "data", "item", "list",
    "form", "page", "view", "type", "name", "value", "error", "result",
}


def find_related_files(
    changed_paths: list,
    project_root: str = ".",
    deleted_contents: dict = None,
) -> dict:
    """
    Scan project for files that import any changed file (direct + 1 level transitive).
    Returns {changed_path: [{"path": str, "content": str, "transitive": bool}]}.
    deleted_contents: {rel_path: old_content} cho các file bị xóa (lấy từ git HEAD).
    """
    project_root = os.path.abspath(project_root)
    graph = _get_graph(project_root)

    # Inject old content của deleted files vào local graph copy để symbol grep hoạt động.
    # Không mutate cache — chỉ tạo shallow copy có thêm entry.
    if deleted_contents:
        extra = {
            rel: {"content": content, "imports": set()}
            for rel, content in deleted_contents.items()
            if rel not in graph and content
        }
        if extra:
            graph = {**graph, **extra}

    result = {p: [] for p in changed_paths}

    for orig_path in changed_paths:
        abs_p = os.path.abspath(orig_path)
        rel_changed = os.path.relpath(abs_p, project_root).replace("\\", "/")

        direct = _find_importers(rel_changed, graph)

        # Layer 2: symbol grep — bắt auto-import và framework-specific usage
        direct |= _find_symbol_users(rel_changed, graph)

        # Với .vue: tìm thêm file nào dùng component này trong <template>
        if Path(orig_path).suffix.lower() == ".vue":
            direct |= _find_vue_template_users(Path(orig_path).stem, graph)

        # Layer 3: framework-specific scanners (React JSX, Angular templateUrl/styleUrls)
        for scanner in _FRAMEWORK_SCANNERS:
            direct |= scanner(rel_changed, graph)

        indirect = set()
        for d in direct:
            for importer in _find_importers(d, graph):
                if importer != rel_changed and importer not in direct:
                    indirect.add(importer)

        seen = set()
        for rel in sorted(direct)[:MAX_RELATED_FILES]:
            seen.add(rel)
            content = graph.get(rel, {}).get("content", "")
            result[orig_path].append({
                "path": rel,
                "content": content[:MAX_RELATED_CONTENT],
                "transitive": False,
            })

        remaining = max(0, MAX_RELATED_FILES - len(seen))
        for rel in sorted(indirect)[:remaining]:
            if rel not in seen:
                seen.add(rel)
                content = graph.get(rel, {}).get("content", "")
                result[orig_path].append({
                    "path": rel,
                    "content": content[:MAX_RELATED_CONTENT],
                    "transitive": True,
                })

    return result


def find_test_files(changed_paths: list, project_root: str = ".") -> list:
    """
    Find test files that correspond to the changed files.
    Returns [{"path": str, "content": str}].
    """
    project_root = os.path.abspath(project_root)
    changed_stems = {Path(p).stem.lower() for p in changed_paths}
    graph = _get_graph(project_root)
    found = []

    for rel, data in graph.items():
        name = Path(rel).name.lower()
        parts = [p.lower() for p in Path(rel).parts]

        in_test_dir = any(part in TEST_DIRS for part in parts)
        is_test_name = any(pat in name for pat in TEST_NAME_PATTERNS)

        if not (in_test_dir or is_test_name):
            continue

        stem = Path(rel).stem.lower()
        stem_clean = re.sub(r"^test[_.]|[_.]test$|[_.]spec$|tests?$|spec$", "", stem, flags=re.IGNORECASE).strip(".")

        if any(cs in stem_clean or stem_clean in cs for cs in changed_stems):
            found.append({
                "path": rel.replace("\\", "/"),
                "content": data.get("content", "")[:MAX_TEST_CONTENT],
            })

        if len(found) >= MAX_TEST_FILES:
            break

    return found


def get_project_structure(project_root: str = ".", max_depth: int = 3) -> str:
    """Return a compact tree of the project directory."""
    root = Path(project_root).resolve()
    lines = [root.name]

    def walk(path: Path, prefix: str, depth: int):
        if depth > max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            return

        visible = [e for e in entries if e.name not in SKIP_DIRS and not e.name.startswith(".")]
        for i, entry in enumerate(visible):
            is_last = i == len(visible) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                extension = "    " if is_last else "│   "
                walk(entry, prefix + extension, depth + 1)

    walk(root, "", 0)
    return "\n".join(lines)


def _build_import_graph(project_root: str) -> dict:
    """
    Scan all project files once.
    Returns {rel_path: {"content": str, "imports": set[str]}}.
    """
    graph = {}
    for fpath in _collect_files(project_root):
        ext = Path(fpath).suffix.lower()
        patterns = IMPORT_PATTERNS.get(ext)
        if not patterns:
            continue
        try:
            text = Path(fpath).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        imports_found = set()
        for pattern in patterns:
            for m in re.finditer(pattern, text, re.MULTILINE):
                for g in m.groups():
                    if g:
                        imp = g.replace("\\", "/")
                        # Python relative import: "from .utils import" → ".utils" → "utils"
                        if ext == ".py":
                            imp = imp.lstrip(".")
                        if imp:
                            imports_found.add(imp)

        rel = os.path.relpath(fpath, project_root).replace("\\", "/")
        graph[rel] = {"content": text, "imports": imports_found}

    return graph


def _find_importers(target_rel: str, graph: dict) -> set:
    """Return rel paths of all files in graph that import target_rel."""
    target_stem = Path(target_rel).stem
    target_rel_no_ext = str(Path(target_rel).with_suffix(""))
    names = {target_stem, target_rel, target_rel_no_ext}

    # Barrel files (index.ts/js, __init__.py) được import qua tên thư mục cha.
    # VD: import '~/components/field' → thực ra là components/field/index.ts
    if target_stem.lower() in ("index", "__init__"):
        parent_dir = str(Path(target_rel_no_ext).parent).replace("\\", "/")
        if parent_dir and parent_dir != ".":
            names.add(parent_dir)

    _seg = re.compile(
        r"(?:^|[/\\@~])(?:" + "|".join(re.escape(n) for n in names) + r")(?:[/\\'\"]|$)"
    )

    importers = set()
    for rel_scan, data in graph.items():
        if rel_scan == target_rel:
            continue
        for imp in data["imports"]:
            # imp.split(".")[-1]: bắt Java/C# dotted import
            # VD: "com.myapp.UserService".split(".")[-1] = "UserService" == target_stem
            if _seg.search(imp) or Path(imp).stem == target_stem or imp.split(".")[-1] == target_stem:
                importers.add(rel_scan)
                break

    return importers


_NAMED_EXPORT_RE = re.compile(r"export\s*\{([^}]+)\}")


def _extract_exports(content: str, ext: str) -> list:
    symbols = []

    # export { Foo, default as Bar } — không bị bắt bởi EXPORT_PATTERNS
    # Quan trọng với barrel file: export { default as GameId } from '~/components/field/GameId.vue'
    if ext in {".js", ".ts", ".jsx", ".tsx", ".vue"}:
        for m in _NAMED_EXPORT_RE.finditer(content):
            for part in m.group(1).split(","):
                part = part.strip()
                if not part:
                    continue
                # "default as CartComp" → "CartComp";  "Foo as Bar" → "Bar";  "Foo" → "Foo"
                exported = part.split(" as ")[-1].strip() if " as " in part else part
                if exported and exported != "default":
                    symbols.append(exported)

    pattern = EXPORT_PATTERNS.get(ext)
    if pattern:
        symbols.extend(pattern.findall(content))

    return [
        s for s in symbols
        if s and len(s) >= MIN_SYMBOL_LEN and s.lower() not in GENERIC_SYMBOLS
        and not s.startswith("_")
    ]


def _find_symbol_users(rel_changed: str, graph: dict) -> set:
    """
    Layer 2: grep tên exported symbol trong toàn project (cùng nhóm ngôn ngữ).
    Bắt được Nuxt auto-import, re-export, và usage không có explicit import.
    """
    ext = Path(rel_changed).suffix.lower()
    allowed_exts = SAME_LANG_EXTS.get(ext)
    if not allowed_exts:
        return set()

    content = graph.get(rel_changed, {}).get("content", "")
    symbols = _extract_exports(content, ext)
    if not symbols:
        return set()

    combined = "|".join(re.escape(s) for s in symbols)
    pattern = re.compile(rf"\b(?:{combined})\b")

    users = set()
    for rel, data in graph.items():
        if rel == rel_changed:
            continue
        if Path(rel).suffix.lower() not in allowed_exts:
            continue
        if pattern.search(data.get("content", "")):
            users.add(rel)

    return users


def _pascal_to_kebab(name: str) -> str:
    """DialogGameUser → dialog-game-user"""
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


_ANGULAR_TEMPLATE_URL_RE = re.compile(r"""templateUrl\s*:\s*['"]([^'"]+)['"]""")
_ANGULAR_STYLE_URLS_RE = re.compile(r"""styleUrls\s*:\s*\[([^\]]*)\]""")
_QUOTED_STRING_RE = re.compile(r"""['"]([^'"]+)['"]""")


def _find_vue_template_users(component_stem: str, graph: dict) -> set:
    """
    Tìm các file .vue đang dùng component này trong template.
    Tìm kiếm toàn file thay vì chỉ trong <template>...</template>
    để tránh bỏ sót khi có <template v-if>, <template v-slot> lồng nhau.
    """
    pascal = component_stem
    kebab = _pascal_to_kebab(component_stem)
    users = set()

    for rel, data in graph.items():
        if not rel.endswith(".vue"):
            continue
        content = data.get("content", "")
        if f"<{pascal}" in content or f"<{kebab}" in content:
            users.add(rel)

    return users


def _find_angular_template_owners(rel_changed: str, graph: dict) -> set:
    """
    Layer 3 — Angular: .html/.scss/.css thay đổi → tìm @Component .ts khai báo templateUrl/styleUrls.
    VD: foo.component.html thay đổi → tìm foo.component.ts có templateUrl: './foo.component.html'
    """
    ext = Path(rel_changed).suffix.lower()
    if ext not in {".html", ".htm", ".scss", ".sass", ".css", ".less"}:
        return set()

    changed_name = Path(rel_changed).name
    changed_stem = Path(rel_changed).stem
    owners = set()

    for rel, data in graph.items():
        if not rel.endswith(".ts"):
            continue
        content = data.get("content", "")
        if "@Component" not in content:
            continue

        m = _ANGULAR_TEMPLATE_URL_RE.search(content)
        if m:
            url = m.group(1)
            if Path(url).name == changed_name or Path(url).stem == changed_stem:
                owners.add(rel)
                continue

        m = _ANGULAR_STYLE_URLS_RE.search(content)
        if m:
            for sm in _QUOTED_STRING_RE.finditer(m.group(1)):
                url = sm.group(1)
                if Path(url).name == changed_name or Path(url).stem == changed_stem:
                    owners.add(rel)
                    break

    return owners


def _find_jsx_template_users(rel_changed: str, graph: dict) -> set:
    """
    Layer 3 — React: .jsx/.tsx component thay đổi → tìm file nào render <ComponentName> trong JSX.
    Chỉ áp dụng khi tên component bắt đầu bằng chữ hoa (React convention).
    """
    ext = Path(rel_changed).suffix.lower()
    if ext not in {".jsx", ".tsx"}:
        return set()

    stem = Path(rel_changed).stem
    if not stem[0].isupper():
        return set()

    kebab = _pascal_to_kebab(stem)
    users = set()

    for rel, data in graph.items():
        if rel == rel_changed:
            continue
        if Path(rel).suffix.lower() not in {".jsx", ".tsx", ".js", ".ts"}:
            continue
        content = data.get("content", "")
        if f"<{stem}" in content or f"<{kebab}" in content:
            users.add(rel)

    return users


_FRAMEWORK_SCANNERS = [_find_jsx_template_users, _find_angular_template_owners]


def _collect_files(root: str) -> list:
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in filenames:
            if len(result) >= MAX_FILES_TO_SCAN:
                return result
            full = os.path.join(dirpath, fname)
            try:
                if os.path.getsize(full) <= MAX_FILE_SIZE:
                    result.append(full)
            except OSError:
                pass
    return result
