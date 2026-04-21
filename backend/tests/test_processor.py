from app.services.processor import MODULAR_TAG_DEFAULTS, DocumentProcessor


def test_modular_tag_defaults_has_required_keys():
    required_keys = [
        "modular_tag_ocr",
        "modular_tag_ocr_fix",
        "modular_tag_title",
        "modular_tag_correspondent",
        "modular_tag_document_type",
        "modular_tag_tags",
        "modular_tag_fields",
        "modular_tag_process",
    ]
    for key in required_keys:
        assert key in MODULAR_TAG_DEFAULTS, f"Missing key: {key}"


def test_modular_tag_defaults_values():
    assert MODULAR_TAG_DEFAULTS["modular_tag_process"] == "ai-process"
    assert MODULAR_TAG_DEFAULTS["modular_tag_fields"] == "ai-fields"
    assert MODULAR_TAG_DEFAULTS["modular_tag_title"] == "ai-title"
