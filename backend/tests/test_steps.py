from app.services.steps.fields_step import FieldsStep, STRUCTURAL_KEYS


def test_structural_keys_excludes_extraction_fields():
    assert "thought" in STRUCTURAL_KEYS
    assert "reasoning" in STRUCTURAL_KEYS
    assert "field" in STRUCTURAL_KEYS
    assert "value" in STRUCTURAL_KEYS
    assert "custom_fields" in STRUCTURAL_KEYS
    assert "extract" in STRUCTURAL_KEYS


def test_extract_fields_from_custom_fields():
    result = {
        "custom_fields": [
            {"field": "Invoice Number", "value": "INV-123"},
            {"field": "Amount", "value": "$500"},
        ]
    }
    fields = FieldsStep._extract_fields_from_result(result)
    assert fields == {"invoice number": "INV-123", "amount": "$500"}


def test_extract_fields_from_extract_key():
    result = {
        "extract": {
            "invoice_number": "INV-123",
            "amount": "$500",
        }
    }
    fields = FieldsStep._extract_fields_from_result(result)
    assert fields == {"invoice number": "INV-123", "amount": "$500"}


def test_extract_fields_skips_empty_values():
    result = {
        "extract": {
            "name": "John",
            "empty_field": "",
        }
    }
    fields = FieldsStep._extract_fields_from_result(result)
    assert "name" in fields
    assert "empty_field" not in fields


def test_extract_fields_skips_structural_keys():
    result = {
        "field": "Name",
        "value": "John",
        "thought": "I think this is a name",
        "reasoning": "Based on context",
    }
    fields = FieldsStep._extract_fields_from_result(result)
    assert "name" in fields
    assert "thought" not in fields
    assert "reasoning" not in fields
