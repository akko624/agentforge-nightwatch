"""Bounded best-effort rules. Uploaded code is never executed.

AST analysis covers aliases, local assignments and known sources/sinks. It is
not a whole-program data-flow or vulnerability engine.
"""

import ast
import io
import json
import math
import re
import time
import tokenize
from collections import Counter
from pathlib import Path, PurePosixPath

import yaml

from backend.app.core.config import get_settings
from backend.app.scan.contracts import AnalysisResult, Finding, ScanContext

_SENSITIVE = re.compile(
    r"(?:~/|\$\{?HOME\}?/|/home/[^/\s]+/)?\.(?:ssh|aws|azure|kube|gnupg)(?:/[^\s\"'`;)]+)?"
    r"|/etc/(?:shadow|passwd)\b|(?:[A-Z]:)?[/\\]Users[/\\][^\s/\\]+[/\\]\.ssh"
    r"|(?:^|[\s\"'(])(?:\.\./)+[^\s\"')]*|(?:^|[/\\])(?:credentials|id_rsa|id_ed25519)\b",
    re.I,
)
_INJECTION = re.compile(
    r"ignore\s+(?:all\s+)?(?:previous|prior|higher[- ]priority|system|developer)\s+(?:instructions?|prompts?|rules?|constraints?)"
    r"|(?:reveal|print|leak|disclose)\s+(?:the\s+)?(?:system|developer|hidden)\s+prompts?"
    r"|忽略.{0,12}(?:高优先级|系统|开发者|先前|之前|上级).{0,8}(?:指令|约束|提示|规则)"
    r"|(?:泄露|输出|打印|显示).{0,8}(?:系统|开发者|隐藏).{0,5}(?:提示词|提示|指令)",
    re.I,
)
_DOWNLOAD_SHELL = re.compile(r"\b(?:curl|wget)\b[^\n|]{0,2048}\|\s*(?:/bin/)?(?:ba|z|da|k)?sh\b", re.I)
_URL = re.compile(r"https?://[^\s\"'`<>]+", re.I)
_NEGATIVE_CONTEXT = re.compile(r"do\s+not|don't|never\s+(?:run|execute|do|use)|unsafe\s+example|anti[- ]example|不要|禁止|反面教材|反例|安全研究", re.I)
_CONFIRM = re.compile(r"(?:explicit|user)\s+(?:approval|confirmation)|confirm\s+(?:with|before|first)|ask\s+(?:the\s+)?user|用户确认|明确确认|确认后|征得.*同意", re.I)
_HIGH_IMPACT = re.compile(r"\brm\s+-[a-z]*r[a-z]*f\b|\brm\s+-[a-z]*f[a-z]*r\b|\b(?:delete|overwrite)\s+(?:all|the|existing)\b|\bsend\s+(?:an?\s+)?(?:email|mail)\b|(?:删除|覆盖)(?:全部|所有|现有)|发送(?:邮件|电子邮件)", re.I)
_REMOTE_INSTRUCTION = re.compile(r"\b(?:execute|run|source|eval|download\s+and\s+(?:run|execute)|follow\s+(?:the\s+)?(?:remote|instructions))\b|(?:执行|运行|遵循|加载).{0,12}(?:远程|指令|脚本)", re.I)
_KNOWN_SECRET = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}|AKIA[A-Z0-9]{16})\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
_SECRET_ASSIGNMENT = re.compile(r"(?i)(?:api[_-]?key|(?:access[_-]?)?token|(?:client[_-]?)?secret|password)\s*[\"']?\s*[:=]\s*[\"']([A-Za-z0-9_+/=-]{16,})[\"']")
_SCRIPT_EXTENSIONS = {".py", ".sh", ".bash", ".zsh", ".ps1", ".js", ".ts", ".mjs", ".cjs", ".rb", ".pl"}
_LOCK_FILES = {"poetry.lock", "uv.lock", "Pipfile.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Cargo.lock", "Gemfile.lock"}
_NETWORK_PREFIXES = ("requests.", "httpx.", "urllib.request.", "urllib3.", "aiohttp.")
_NETWORK_METHODS = {"get", "post", "put", "patch", "delete", "request", "urlopen", "urlretrieve", "connect", "send", "sendall", "sendto"}
_SCRIPT_NETWORK = re.compile(r"\b(?:curl|wget|Invoke-WebRequest|Invoke-RestMethod)\b|\b(?:fetch|axios\.(?:get|post|put|delete|request)|https?\.(?:get|request))\s*\(", re.I)
_MAX_AST_BYTES = 2 * 1024 * 1024
_MAX_AST_NODES = 50000
_MAX_FINDINGS = 2000


def load_rules(path: Path | str | None = None) -> dict:
    """Load platform-owned configuration, never a ZIP-provided rules file."""
    source = Path(path) if path is not None else get_settings().rules_path
    ruleset = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(ruleset, dict) or len(ruleset.get("rules", [])) != 16:
        raise ValueError("Builtin ruleset must contain sixteen versioned rules")
    return ruleset


def _entropy(value: str) -> float:
    counts = Counter(value)
    return -sum((count / len(value)) * math.log2(count / len(value)) for count in counts.values())


def _call_name(node: ast.AST, aliases: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value, aliases)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _call_name(node.func, aliases)
    return ""


def _constants(node: ast.AST) -> list[str]:
    return [item.value for item in ast.walk(node) if isinstance(item, ast.Constant) and isinstance(item.value, str)]


def _is_network_call(node: ast.Call, aliases: dict[str, str]) -> bool:
    name = _call_name(node.func, aliases)
    method = name.rsplit(".", 1)[-1]
    return method in _NETWORK_METHODS and (name.startswith(_NETWORK_PREFIXES) or name.startswith("socket."))


def _sensitive_source(node: ast.AST, aliases: dict[str, str]) -> bool:
    for item in ast.walk(node):
        if isinstance(item, ast.Call):
            name = _call_name(item.func, aliases)
            reads_file = name in {"open", "io.open"} or name.endswith((".read_text", ".read_bytes", ".read"))
            if name in {"open", "io.open"}:
                mode = next((keyword.value for keyword in item.keywords if keyword.arg == "mode"), item.args[1] if len(item.args) > 1 else None)
                if isinstance(mode, ast.Constant) and isinstance(mode.value, str) and any(char in mode.value for char in "wax") and "+" not in mode.value:
                    reads_file = False
            if reads_file and any(_SENSITIVE.search(value) for value in _constants(item)):
                return True
            if name in {"os.getenv", "os.environ.get"} and any(re.search(r"TOKEN|SECRET|PASSWORD|KEY", value, re.I) for value in _constants(item)):
                return True
        if isinstance(item, ast.Subscript) and _call_name(item.value, aliases) == "os.environ" and any(re.search(r"TOKEN|SECRET|PASSWORD|KEY", value, re.I) for value in _constants(item.slice)):
            return True
    return False


def _tainted(node: ast.AST, names: set[str], aliases: dict[str, str], *, secrets: bool = False) -> bool:
    if secrets and _sensitive_source(node, aliases):
        return True
    for item in ast.walk(node):
        if isinstance(item, ast.Name) and item.id in names:
            return True
        if not secrets and isinstance(item, ast.Call) and _call_name(item.func, aliases) in {"input", "builtins.input"}:
            return True
        if not secrets and isinstance(item, ast.Subscript) and _call_name(item.value, aliases) in {"sys.argv", "os.environ"}:
            return True
    return False


class BuiltinStaticAnalyzer:
    name = "builtin-static"

    def __init__(self) -> None:
        self.ruleset = load_rules()
        self.rules = {rule["id"]: rule for rule in self.ruleset["rules"]}

    def analyze(self, context: ScanContext) -> AnalysisResult:
        started = time.perf_counter()
        findings: list[Finding] = []
        unsupported: list[str] = []
        ast_errors: list[dict] = []
        python_total = python_parsed = 0
        text_files: dict[str, str] = {}
        file_lines: dict[str, list[str]] = {}
        comment_lines: dict[str, set[int]] = {}
        network_calls: list[tuple[str, int, int]] = []
        candidate_limit_hit = False

        def emit(rule_id: str, path: str, line: int = 1, end: int | None = None, *, evidence: str | None = None,
                 message: str | None = None, confidence: str = "MEDIUM", note: str | None = None, severity: str | None = None) -> None:
            nonlocal candidate_limit_hit
            if len(findings) >= _MAX_FINDINGS:
                candidate_limit_hit = True
                return
            rule = self.rules[f"SQSP-{rule_id}"]
            lines = file_lines.get(path, [])
            end = end or line
            snippet = evidence if evidence is not None else "\n".join(lines[max(0, line - 1):min(end, line + 4)])
            vicinity = "\n".join(lines[max(0, line - 3):min(len(lines), end + 1)])
            is_comment = line in comment_lines.get(path, set())
            negative = bool(_NEGATIVE_CONTEXT.search(vicinity))
            if is_comment or negative:
                confidence = "LOW"
                note = "Comment or negative-example context; candidate for human review, not confirmed malicious behavior."
                if severity == "CRITICAL" or rule["severity"] == "CRITICAL":
                    severity = "HIGH"
            findings.append(Finding(
                rule_id=rule["id"], category=rule["category"], severity=severity or rule["severity"], confidence=confidence,
                file_path=path, line_start=max(1, line), line_end=max(line, end), evidence_excerpt=snippet,
                message=message or rule["title"], remediation=rule["remediation"], context_note=note,
                matched_rule_version=self.ruleset["version"], engine_version=self.ruleset["engine_version"],
            ).safe())

        inventory = {item["path"]: item for item in context.inventory}
        for path, data in sorted(context.files.items()):
            item = inventory.get(path, {})
            if item.get("kind") in {"binary", "archive"} or item.get("parseable") is False or b"\0" in data:
                unsupported.append(path)
                emit("S004", path, evidence=f"Unsupported {item.get('kind', 'binary')} payload; {len(data)} bytes.", confidence="HIGH")
                continue
            try:
                text_files[path] = data.decode("utf-8-sig", errors="strict")
                file_lines[path] = text_files[path].splitlines()
            except UnicodeError:
                unsupported.append(path)
                emit("S004", path, evidence="Unsupported text encoding; byte content was not interpreted.", confidence="HIGH")
                continue
            if PurePosixPath(path).suffix.lower() == ".py":
                try:
                    comments = tokenize.generate_tokens(io.StringIO(text_files[path]).readline)
                    comment_lines[path] = {tok.start[0] for tok in comments if tok.type == tokenize.COMMENT and not file_lines[path][tok.start[0] - 1][:tok.start[1]].strip()}
                except (tokenize.TokenError, IndentationError):
                    comment_lines[path] = set()
            elif PurePosixPath(path).suffix.lower() in _SCRIPT_EXTENSIONS:
                comment_lines[path] = {i for i, line in enumerate(text_files[path].splitlines(), 1) if line.lstrip().startswith(("#", "//", "/*", "*"))}

        network_denied = context.parsed.security.get("security", {}).get("network", {}).get("mode", "deny") == "deny"
        for path, text in sorted(text_files.items()):
            lines = file_lines[path]
            suffix = PurePosixPath(path).suffix.lower()
            for number, line in enumerate(lines, 1):
                if _INJECTION.search(line):
                    emit("S005", path, number)
                if _SENSITIVE.search(line):
                    emit("S006", path, number)
                if _KNOWN_SECRET.search(line) or any(_entropy(match.group(1)) >= 3.5 for match in _SECRET_ASSIGNMENT.finditer(line)):
                    emit("S007", path, number, evidence="[REDACTED] Suspected credential material on this line.", confidence="MEDIUM")
                if _HIGH_IMPACT.search(line) and not _CONFIRM.search(text) and not context.parsed.security.get("security", {}).get("destructive_actions", {}).get("confirmation_required", False):
                    emit("S013", path, number, confidence="MEDIUM")
                if _URL.search(line) and (_REMOTE_INSTRUCTION.search(line) or _DOWNLOAD_SHELL.search(line)) and not re.search(r"(?:sha256[:= ]+[a-f0-9]{64}|/commit/[a-f0-9]{40}|/raw/[a-f0-9]{40}|@[a-f0-9]{40})", line, re.I):
                    emit("S008", path, number, confidence="LOW", note="Mutable remote instructions inferred from text; ordinary reference links are not matched.")

            logical = []
            logical_lines = []
            for number, line in enumerate(lines, 1):
                logical.append(re.sub(r"\\\s*$", " ", line))
                logical_lines.append(number)
                if re.search(r"\\\s*$", line):
                    continue
                joined = " ".join(logical)
                if _DOWNLOAD_SHELL.search(joined):
                    emit("S002", path, logical_lines[0], number)
                if suffix in _SCRIPT_EXTENSIONS - {".py"} and logical_lines[0] not in comment_lines.get(path, set()):
                    if _SCRIPT_NETWORK.search(joined):
                        network_calls.append((path, logical_lines[0], number))
                        if _SENSITIVE.search(joined) and re.search(r"(?:--data(?:-binary)?\s+@|(?:-d|-F|--upload-file|-T)\s+@?)", joined):
                            emit("S001", path, logical_lines[0], number, confidence="HIGH")
                logical, logical_lines = [], []

            if suffix != ".py":
                continue
            python_total += 1
            if len(context.files[path]) > _MAX_AST_BYTES:
                ast_errors.append({"file_path": path, "reason": "python_ast_size_limit"})
                continue
            try:
                tree = ast.parse(text, filename="untrusted-skill.py")
                nodes = []
                for node in ast.walk(tree):
                    nodes.append(node)
                    if len(nodes) > _MAX_AST_NODES:
                        raise ValueError("python_ast_node_limit")
            except (SyntaxError, ValueError, RecursionError, MemoryError) as error:
                reason = "python_syntax_error" if isinstance(error, SyntaxError) else "python_ast_resource_limit"
                ast_errors.append({"file_path": path, "reason": reason, "line": getattr(error, "lineno", None)})
                continue
            python_parsed += 1
            aliases: dict[str, str] = {}
            for node in nodes:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        aliases[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
            secret_names: set[str] = set()
            input_names: set[str] = set()
            for _ in range(3):
                for node in nodes:
                    if not isinstance(node, ast.Assign | ast.AnnAssign):
                        continue
                    value = node.value
                    if value is None:
                        continue
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    names = {item.id for target in targets for item in ast.walk(target) if isinstance(item, ast.Name)}
                    if _tainted(value, secret_names, aliases, secrets=True):
                        secret_names |= names
                    if _tainted(value, input_names, aliases):
                        input_names |= names
                    if isinstance(value, ast.Call) and _call_name(value.func, aliases) in {"requests.Session", "httpx.Client", "httpx.AsyncClient"}:
                        for name in names:
                            aliases[name] = _call_name(value.func, aliases).split(".")[0]
            for node in nodes:
                if not isinstance(node, ast.Call):
                    continue
                name = _call_name(node.func, aliases)
                line, end = node.lineno, getattr(node, "end_lineno", node.lineno)
                if name in {"eval", "exec", "builtins.eval", "builtins.exec", "os.system", "os.popen"} or (name.startswith("subprocess.") and any(keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True for keyword in node.keywords)):
                    emit("S003", path, line, end, confidence="HIGH", note="AST call candidate; dynamic execution may be intentional and requires context review.")
                if _is_network_call(node, aliases):
                    network_calls.append((path, line, end))
                    payloads = list(node.args) + [keyword.value for keyword in node.keywords]
                    if any(_tainted(payload, secret_names, aliases, secrets=True) for payload in payloads):
                        emit("S001", path, line, end, confidence="HIGH", evidence="Credential source -> local assignment -> known network sink (evidence redacted).")
                write_target = None
                if name in {"open", "io.open"} and node.args:
                    mode = next((keyword.value for keyword in node.keywords if keyword.arg == "mode"), node.args[1] if len(node.args) > 1 else None)
                    if isinstance(mode, ast.Constant) and isinstance(mode.value, str) and any(char in mode.value for char in "wax+"):
                        write_target = node.args[0]
                elif name.endswith((".write_text", ".write_bytes")) and isinstance(node.func, ast.Attribute):
                    write_target = node.func.value
                if write_target is not None and _tainted(write_target, input_names, aliases):
                    emit("S010", path, line, end, confidence="LOW", note="Local input-to-write-path flow only; containment validation and interprocedural flows require review.")
                if PurePosixPath(path).name == "setup.py" and (name.startswith("subprocess.") or name in {"os.system", "os.popen", "eval", "exec"}):
                    emit("S012", path, line, end)
                if (name in {"os.remove", "os.unlink", "shutil.rmtree"} or name.endswith((".unlink", ".rmdir", ".sendmail", ".send_message"))) and not _CONFIRM.search(text) and not context.parsed.security.get("security", {}).get("destructive_actions", {}).get("confirmation_required", False):
                    emit("S013", path, line, end, confidence="MEDIUM", note="AST high-impact operation; review approval requirements in the trusted host.")

        if network_denied:
            for path, line, end in network_calls:
                emit("S009", path, line, end, confidence="HIGH", note="A declaration is not a runtime permission grant; dynamic enforcement was not run.")

        dependency_partial = self._dependencies(context, text_files, emit)
        security = context.parsed.security.get("security", {})
        broad = security.get("environment", {}).get("secret_access", False)
        filesystem = security.get("filesystem", {})
        broad = broad or any(path in {"${HOME}/**", "${WORKSPACE}/**"} for mode in ("read", "write") for path in filesystem.get(mode, []))
        tools = context.parsed.frontmatter.get("allowed-tools", "")
        broad = broad or bool(re.search(r"(?:^|\s)(?:\*|Bash|Shell|Exec)(?:\s|$|\([^)]*\*[^)]*\))", tools, re.I))
        if broad:
            emit("S014", "skill-security.yaml" if context.parsed.security else "SKILL.md", confidence="LOW", evidence="Broad filesystem, secret or tool capability requested.", note="Deterministic permission-width heuristic only; task necessity requires human review.")
        body = context.parsed.body
        if (re.search(r"\b(?:tool|cli|command|curl|python|npm|pip|requires?)\b|外部工具|命令|依赖", body, re.I)
                and not re.search(r"\b(?:error|fail|timeout|retry|unavailable|exception)\b|失败|错误|超时|重试|不可用", body, re.I)):
            emit("S015", "SKILL.md", confidence="LOW", evidence="External-tool instructions have no recognizable failure/timeout handling section.")
        missing = []
        if not context.parsed.evals.get("cases"):
            missing.append("evaluation cases")
        if not context.parsed.frontmatter.get("license") and not any(PurePosixPath(path).name.lower().startswith(("license", "copying")) for path in context.files):
            missing.append("license")
        if not context.parsed.frontmatter.get("metadata", {}).get("version"):
            missing.append("version metadata")
        if missing:
            emit("S016", "SKILL.md", confidence="HIGH", evidence="Missing: " + ", ".join(missing), note="Maintainability/coverage information, not a security vulnerability or runtime test result.")
        unique = {finding.fingerprint: finding for finding in findings}
        result = sorted(unique.values(), key=lambda finding: (finding.file_path, finding.line_start, finding.rule_id, finding.fingerprint))
        partial = bool(unsupported or ast_errors or dependency_partial or candidate_limit_hit)
        return AnalysisResult(
            status="PARTIAL" if partial else "FINDINGS" if result else "PASSED", findings=result,
            reason="Static coverage is incomplete; inspect coverage details." if partial else None,
            duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
            coverage={"files_total": len(context.files), "files_scanned": len(text_files), "unsupported_files": unsupported,
                      "python_ast_total": python_total, "python_ast_parsed": python_parsed, "python_ast_errors": ast_errors,
                      "finding_limit_reached": candidate_limit_hit, "finding_limit": _MAX_FINDINGS,
                      "dependency_status": "PARTIAL" if dependency_partial else "NOT_RUN",
                      "dependency_reason": "Version/lock coverage incomplete; no vulnerability database queried." if dependency_partial else "No vulnerability database queried; this engine does not provide CVE coverage.",
                      "dataflow_scope": "Local assignment propagation (3 passes), known Python sources/sinks; no whole-program proof."},
        )

    def _dependencies(self, context: ScanContext, texts: dict[str, str], emit) -> bool:
        partial = False
        for path, text in texts.items():
            name = PurePosixPath(path).name
            parent = str(PurePosixPath(path).parent)
            siblings = {PurePosixPath(item).name for item in context.files if str(PurePosixPath(item).parent) == parent}
            if name == "package.json":
                try:
                    package = json.loads(text)
                except (ValueError, TypeError, RecursionError):
                    partial = True
                    emit("S011", path, evidence="package.json could not be parsed; dependency coverage incomplete.", confidence="HIGH")
                    continue
                if not isinstance(package, dict):
                    partial = True
                    emit("S011", path, evidence="package.json is not an object; dependency coverage incomplete.", confidence="HIGH")
                    continue
                dependencies = dict(package.get("dependencies", {})) if isinstance(package.get("dependencies", {}), dict) else {}
                if isinstance(package.get("devDependencies", {}), dict):
                    dependencies.update(package.get("devDependencies", {}))
                unpinned = [key for key, value in dependencies.items() if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", value)]
                if dependencies and (unpinned or not siblings.intersection(_LOCK_FILES)):
                    partial = True
                    emit("S011", path, evidence="Dependency versions are mutable or no supported lock file is present; CVEs were not evaluated.", confidence="HIGH")
                scripts = package.get("scripts", {})
                if isinstance(scripts, dict):
                    for hook in ("preinstall", "install", "postinstall", "prepare"):
                        if isinstance(scripts.get(hook), str) and scripts[hook].strip():
                            emit("S012", path, evidence=f"Non-empty dependency lifecycle hook: {hook}.", confidence="MEDIUM")
            elif re.fullmatch(r"requirements(?:[-_.][\w-]+)?\.txt", name, re.I):
                declarations = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
                unpinned = [line for line in declarations if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:\[[^]]+\])?==[^\s*<>~;]+(?:\s*;[^\n]+)?", line)]
                if unpinned:
                    partial = True
                    emit("S011", path, evidence="Unpinned or unsupported requirement declaration; dependency/CVE coverage incomplete.", confidence="HIGH")
            elif name in {"pyproject.toml", "Pipfile", "setup.cfg", "Gemfile", "Cargo.toml"} and not siblings.intersection(_LOCK_FILES):
                partial = True
                emit("S011", path, evidence="Dependency manifest has no supported lock file; dependency/CVE coverage incomplete.", confidence="MEDIUM")
        return partial
