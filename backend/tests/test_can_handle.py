"""Unit tests for Step.can_handle() logic — no DB, no network."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.steps.ocr_step import OCRStep
from app.services.steps.ocr_fix_step import OCRFixStep
from app.services.steps.title_step import TitleStep
from app.services.steps.correspondent_step import CorrespondentStep
from app.services.steps.document_type_step import DocumentTypeStep
from app.services.steps.tags_step import TagsStep
from app.services.steps.fields_step import FieldsStep
from app.services.steps.modular_tags_step import ModularTagsStep


CONFIG = {
    "force_ocr_tag": "force_ocr",
    "force_ocr_fix_tag": "force-ocr-fix",
    "modular_tag_process": "ai-process",
    "modular_tag_title": "ai-title",
    "modular_tag_correspondent": "ai-correspondent",
    "modular_tag_document_type": "ai-document-type",
    "modular_tag_tags": "ai-tags",
    "modular_tag_fields": "ai-fields",
}


# --- OCRStep ---

def test_ocr_step_triggers_on_force_ocr_tag():
    step = OCRStep(CONFIG)
    assert step.can_handle({"force_ocr"}) is True

def test_ocr_step_does_not_trigger_on_fix_tag_only():
    """OCRStep must NOT run when only the fix tag is present."""
    step = OCRStep(CONFIG)
    assert step.can_handle({"force-ocr-fix"}) is False

def test_ocr_step_ignores_ai_process():
    step = OCRStep(CONFIG)
    assert step.can_handle({"ai-process"}) is False


# --- OCRFixStep ---

def test_ocr_fix_step_triggers_on_fix_tag():
    step = OCRFixStep(CONFIG)
    assert step.can_handle({"force-ocr-fix"}) is True

def test_ocr_fix_step_triggers_when_ocr_will_run():
    """OCRFixStep should also run when force_ocr_tag is present (piggybacks on OCR pass)."""
    step = OCRFixStep(CONFIG)
    assert step.can_handle({"force_ocr"}) is True


# --- Classification steps: must trigger on ai-process ---

def test_title_step_triggers_on_ai_process():
    step = TitleStep(CONFIG)
    assert step.can_handle({"ai-process"}) is True

def test_title_step_triggers_on_specific_tag():
    step = TitleStep(CONFIG)
    assert step.can_handle({"ai-title"}) is True

def test_title_step_ignores_unrelated_tag():
    step = TitleStep(CONFIG)
    assert step.can_handle({"something-else"}) is False

def test_correspondent_step_triggers_on_ai_process():
    step = CorrespondentStep(CONFIG)
    assert step.can_handle({"ai-process"}) is True

def test_correspondent_step_triggers_on_specific_tag():
    step = CorrespondentStep(CONFIG)
    assert step.can_handle({"ai-correspondent"}) is True

def test_correspondent_step_ignores_unrelated_tag():
    step = CorrespondentStep(CONFIG)
    assert step.can_handle({"something-else"}) is False

def test_document_type_step_triggers_on_ai_process():
    step = DocumentTypeStep(CONFIG)
    assert step.can_handle({"ai-process"}) is True

def test_document_type_step_triggers_on_specific_tag():
    step = DocumentTypeStep(CONFIG)
    assert step.can_handle({"ai-document-type"}) is True

def test_document_type_step_ignores_unrelated_tag():
    step = DocumentTypeStep(CONFIG)
    assert step.can_handle({"something-else"}) is False

def test_tags_step_triggers_on_ai_process():
    step = TagsStep(CONFIG)
    assert step.can_handle({"ai-process"}) is True

def test_tags_step_triggers_on_specific_tag():
    step = TagsStep(CONFIG)
    assert step.can_handle({"ai-tags"}) is True

def test_tags_step_ignores_unrelated_tag():
    step = TagsStep(CONFIG)
    assert step.can_handle({"something-else"}) is False

def test_fields_step_triggers_on_ai_process():
    step = FieldsStep(CONFIG)
    assert step.can_handle({"ai-process"}) is True

def test_fields_step_triggers_on_specific_tag():
    step = FieldsStep(CONFIG)
    assert step.can_handle({"ai-fields"}) is True

def test_fields_step_ignores_unrelated_tag():
    step = FieldsStep(CONFIG)
    assert step.can_handle({"something-else"}) is False


# --- ModularTagsStep: reads process tag from config ---

def test_modular_tags_step_triggers_on_configured_process_tag():
    step = ModularTagsStep(CONFIG)
    assert step.can_handle({"ai-process"}) is True

def test_modular_tags_step_triggers_on_individual_step_tags():
    # ModularTagsStep must also run for individual step tags so it can remove them
    step = ModularTagsStep(CONFIG)
    assert step.can_handle({"ai-title"}) is True
    assert step.can_handle({"ai-correspondent"}) is True
    assert step.can_handle({"ai-tags"}) is True

def test_modular_tags_step_ignores_unrelated_tags():
    step = ModularTagsStep(CONFIG)
    assert step.can_handle({"Rechnung"}) is False
    assert step.can_handle(set()) is False
