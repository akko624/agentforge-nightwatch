import pytest

from backend.app.core.errors import PlatformError
from backend.app.skill.parser import load_yaml, parse_skill


def skill(name="test-skill", extra="", body="# Test\n1. Read input.\n2. Write output.\n"):
    return {"SKILL.md": f"---\nname: {name}\ndescription: Use when summarizing a local file.\n{extra}---\n{body}".encode()}


def test_valid_and_directory_name():
    result = parse_skill(skill(extra='metadata:\n  version: "1.0"\n'), "test-skill")
    assert result.manifest["metadata"]["version"] == "1.0"
    with pytest.raises(PlatformError, match="directory"):
        parse_skill(skill(), "different")


@pytest.mark.parametrize("name", ["bad--name", "-bad", "bad-", "Bad", "a" * 65, "bad_name"])
def test_invalid_names(name):
    with pytest.raises(PlatformError) as error:
        parse_skill(skill(name))
    assert error.value.code == "INVALID_SKILL_NAME"


@pytest.mark.parametrize("data", ["x: !!python/object:os.system {}", "x: &x [1]\ny: *x", "x: 1\nx: 2", "x: " + "[" * 20 + "0" + "]" * 20])
def test_yaml_rejects_tags_aliases_duplicates_depth(data):
    with pytest.raises(PlatformError):
        load_yaml(data)


def test_metadata_string_and_description_boundaries():
    with pytest.raises(PlatformError) as error:
        parse_skill(skill(extra="metadata:\n  version: 1\n"))
    assert error.value.code == "INVALID_METADATA"
    files = skill()
    files["SKILL.md"] = b"---\nname: test-skill\ndescription: " + b"a" * 1025 + b"\n---\n"
    with pytest.raises(PlatformError):
        parse_skill(files)


def test_resource_references_are_package_local():
    result = parse_skill(skill(body="[bad](../../host)\n[missing](scripts/foo.py)\n[web](https://example.invalid)"))
    assert {i["code"] for i in result.issues} == {"UNSAFE_REFERENCE", "MISSING_REFERENCE"}


def test_sidecars_and_fixture_escape():
    files = skill()
    files["skill-security.yaml"] = b"schema_version: '1.0'\nsecurity:\n  subprocess:\n    allowed: 'yes'"
    with pytest.raises(PlatformError) as error:
        parse_skill(files)
    assert error.value.code == "INVALID_SECURITY_DECLARATION"
    files.pop("skill-security.yaml")
    files["evals/cases.yaml"] = b"schema_version: '1.0'\ncases:\n- id: x\n  name: test\n  category: functional\n  trigger_prompt: test\n  expected: {}\n  fixtures:\n  - source: ../../host\n    target: inputs/x"
    with pytest.raises(PlatformError) as error:
        parse_skill(files)
    assert error.value.code == "INVALID_EVALS"


def test_path_templates_reject_arbitrary_variables():
    files = skill()
    files["skill-security.yaml"] = b"schema_version: '1.0'\nsecurity:\n  filesystem:\n    read: ['${ARBITRARY}/**']"
    with pytest.raises(PlatformError):
        parse_skill(files)
