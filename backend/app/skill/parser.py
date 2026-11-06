import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

import yaml
from jsonschema import Draft202012Validator

from backend.app.core.config import ROOT
from backend.app.core.errors import PlatformError
from backend.app.core.redaction import redact_object


class UniqueSafeLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        mapping = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in mapping:
                raise ValueError("Duplicate or non-string mapping key")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def load_yaml(data: bytes | str, *, code: str = "UNSAFE_YAML", max_bytes: int = 65536):
    if isinstance(data, str):
        data = data.encode("utf-8")
    if len(data) > max_bytes:
        raise PlatformError(code, "YAML exceeds size limit")
    try:
        text = data.decode("utf-8", errors="strict")
        depth = nodes = 0
        for event in yaml.parse(text, Loader=UniqueSafeLoader):
            nodes += 1
            if nodes > 5000 or isinstance(event, yaml.AliasEvent):
                raise ValueError("Aliases or excessive YAML nodes")
            if isinstance(event, yaml.MappingStartEvent | yaml.SequenceStartEvent):
                depth += 1
                if depth > 12:
                    raise ValueError("YAML nesting too deep")
            elif isinstance(event, yaml.MappingEndEvent | yaml.SequenceEndEvent):
                depth -= 1
        return yaml.load(text, Loader=UniqueSafeLoader)
    except (yaml.YAMLError, ValueError, UnicodeError, TypeError, RecursionError):
        raise PlatformError(code, "YAML is invalid or unsafe") from None


def local_reference(value: str) -> str | None:
    value = unquote(value.split("#", 1)[0].split("?", 1)[0])
    if not value or urlsplit(value).scheme in {"http", "https", "mailto"}:
        return None
    if any(char in value for char in ("\\", "\x00", ":")) or value.startswith("/"):
        raise ValueError("Unsafe local reference")
    path = PurePosixPath(value)
    if ".." in path.parts:
        raise ValueError("Reference leaves Skill")
    return str(path)


@dataclass
class ParsedSkill:
    name: str
    body: str
    frontmatter: dict
    security: dict
    evals: dict
    issues: list[dict]
    manifest: dict


def validate_sidecar(files: dict[str, bytes], path: str, schema_name: str, code: str) -> dict:
    if path not in files:
        return {}
    data = load_yaml(files[path], code=code)
    schema = json.loads((ROOT / "schemas" / schema_name).read_text("utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(data))
    if errors:
        raise PlatformError(code, "Sidecar does not match SQSP schema", details={
            "paths": ["/".join(map(str, e.absolute_path)) for e in errors[:10]],
        })
    return data


def parse_skill(files: dict[str, bytes], root_name: str | None = None) -> ParsedSkill:
    try:
        text = files["SKILL.md"].decode("utf-8-sig", errors="strict")
    except (KeyError, UnicodeError):
        raise PlatformError("INVALID_SKILL", "SKILL.md must be UTF-8") from None
    match = re.match(r"\A---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)", text)
    if not match:
        raise PlatformError("INVALID_FRONTMATTER", "SKILL.md requires YAML frontmatter")
    frontmatter = load_yaml(match.group(1))
    if not isinstance(frontmatter, dict):
        raise PlatformError("INVALID_FRONTMATTER", "Frontmatter must be a mapping")
    name, description = frontmatter.get("name"), frontmatter.get("description")
    if not isinstance(name, str) or not 1 <= len(name) <= 64 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise PlatformError("INVALID_SKILL_NAME", "Invalid Skill name")
    if root_name is not None and name != root_name:
        raise PlatformError("SKILL_NAME_MISMATCH", "Skill name must match its parent directory")
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        raise PlatformError("INVALID_DESCRIPTION", "Description must contain 1 to 1024 characters")
    metadata = frontmatter.get("metadata", {})
    if not isinstance(metadata, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in metadata.items()):
        raise PlatformError("INVALID_METADATA", "Metadata must map strings to strings")
    if len(metadata.get("version", "")) > 64:
        raise PlatformError("INVALID_METADATA", "Version label exceeds 64 characters")
    for optional in ("license", "compatibility", "allowed-tools"):
        if optional in frontmatter and not isinstance(frontmatter[optional], str):
            raise PlatformError("INVALID_FRONTMATTER", "Optional frontmatter field must be a string")
    if len(frontmatter.get("compatibility", "")) > 500:
        raise PlatformError("INVALID_FRONTMATTER", "Compatibility exceeds 500 characters")
    security = validate_sidecar(files, "skill-security.yaml", "skill-security.schema.json", "INVALID_SECURITY_DECLARATION")
    evals = validate_sidecar(files, "evals/cases.yaml", "skill-evals.schema.json", "INVALID_EVALS")
    issues = []
    # Resolve Markdown and inline resource references without reading the host filesystem.
    for path, data in files.items():
        if not path.lower().endswith(".md"):
            continue
        try:
            content = data.decode("utf-8")
        except UnicodeError:
            continue  # Inventory and static coverage record unsupported encodings separately.
        matches = list(re.finditer(r"!?\[[^\]]*\]\(\s*<?([^\s)>]+)>?(?:\s+[^)]*)?\)", content))
        matches += list(re.finditer(r"`((?:scripts|references|assets|fixtures|evals)/[^`\n]+)`", content))
        for ref in matches:
            value = ref.group(1)
            line = content.count("\n", 0, ref.start()) + 1
            try:
                target = local_reference(value)
                if target is None:
                    continue
                target = str(PurePosixPath(path).parent / target)
                if target not in files and not any(p.startswith(target.rstrip("/") + "/") for p in files):
                    issues.append({"code": "MISSING_REFERENCE", "file_path": path, "line": line})
            except ValueError:
                issues.append({"code": "UNSAFE_REFERENCE", "file_path": path, "line": line})
    seen_ids = set()
    for case in evals.get("cases", []):
        if case["id"] in seen_ids:
            raise PlatformError("INVALID_EVALS", "Duplicate evaluation case ID")
        seen_ids.add(case["id"])
        for fixture in case.get("fixtures", []):
            try:
                source, target = local_reference(fixture["source"]), local_reference(fixture["target"])
                if source is None or target is None or source not in files:
                    raise ValueError()
            except ValueError:
                raise PlatformError("INVALID_EVALS", "Fixtures must reference existing package-local files and safe targets") from None
        output_file = case.get("expected", {}).get("output_file")
        if output_file:
            try:
                if local_reference(output_file) is None:
                    raise ValueError()
            except ValueError:
                raise PlatformError("INVALID_EVALS", "Expected output must be package-local") from None
    body = text[match.end():]
    manifest = redact_object({
        "name": name, "description": description, "metadata": metadata,
        "license": frontmatter.get("license"), "standards_version": "agentskills-2026-11",
        "platform_policy_version": "1.0", "issues": issues,
        "security_declared": bool(security), "eval_case_count": len(evals.get("cases", [])),
        "allowed_tools_experimental": frontmatter.get("allowed-tools"),
    })
    return ParsedSkill(name, body, frontmatter, security, evals, issues, manifest)
