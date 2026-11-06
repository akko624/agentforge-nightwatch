import pytest

from scripts.generate_api_types import ts_type


def test_openapi_codegen_preserves_null_and_required_fields():
    result = ts_type({"type": "object", "properties": {"score": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                                                      "name": {"type": "string"}}, "required": ["score"]})
    assert '"score": (number | null)' in result
    assert '"name"?: string' in result
    assert ts_type({"$ref": "#/components/schemas/Finding"}) == 'components["schemas"]["Finding"]'


def test_codegen_fails_on_unsupported_constructs():
    with pytest.raises(ValueError):
        ts_type({"not": {"type": "string"}})
    with pytest.raises(ValueError):
        ts_type({"$ref": "https://example.invalid/schema"})
