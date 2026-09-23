"""Tags the pipeline reacts to or sets itself.

They live in the same Paperless tag list as the tags that describe a document,
so the tags step used to offer them to the model like any other. A picked
ai-ocr sent the document through vision OCR again on the next pass and
overwrote its content, and a picked force_ocr was never taken off again.
"""

from typing import Any, Iterable, Mapping

MODULAR_TAG_DEFAULTS: dict[str, str] = {
    "modular_tag_ocr": "ai-ocr",
    "modular_tag_ocr_fix": "ai-ocr-fix",
    "modular_tag_date": "ai-date",
    "modular_tag_title": "ai-title",
    "modular_tag_correspondent": "ai-correspondent",
    "modular_tag_document_type": "ai-document-type",
    "modular_tag_tags": "ai-tags",
    "modular_tag_fields": "ai-fields",
    "modular_tag_process": "ai-process",
}

FORCE_TAG_DEFAULTS: dict[str, str] = {
    "force_ocr_tag": "force_ocr",
    "force_ocr_fix_tag": "force-ocr-fix",
}


def control_tag_names(config: Mapping[str, Any]) -> set[str]:
    """Lower-cased names of every tag that drives or marks processing."""
    names = [config.get(key) or default for key, default in MODULAR_TAG_DEFAULTS.items()]
    names += [config.get(key) or default for key, default in FORCE_TAG_DEFAULTS.items()]
    names += [config.get("process_tag"), config.get("processed_tag")]
    return {str(name).strip().lower() for name in names if name and str(name).strip()}


def blacklisted_tag_names(config: Mapping[str, Any]) -> set[str]:
    """Lower-cased names from the comma-separated tag_blacklist setting."""
    raw = config.get("tag_blacklist") or ""
    return {name.strip().lower() for name in str(raw).split(",") if name.strip()}


def assignable_tags(tags: Iterable[dict], config: Mapping[str, Any]) -> list[dict]:
    """The tags the model may choose from: no control tags, nothing blacklisted."""
    excluded = control_tag_names(config) | blacklisted_tag_names(config)
    return [tag for tag in tags if str(tag.get("name", "")).strip().lower() not in excluded]
