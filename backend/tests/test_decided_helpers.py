"""The settings the decision steps read per document, with their defaults."""

from app.services.decision import Decision
from app.services.steps.base import StepContext, StepResult
from app.services.steps.decided import (
    DEFAULT_THRESHOLD,
    decision_details,
    decision_enabled,
    decision_question,
    decision_threshold,
    review,
)


def test_toggles_default_off():
    assert decision_enabled({}, "correspondent") is False
    assert decision_enabled({"decision_correspondent": "true"}, "correspondent") is True
    assert decision_enabled({"decision_correspondent": "True "}, "correspondent") is True


def test_thresholds_default_and_clamp():
    assert decision_threshold({}, "document_type") == DEFAULT_THRESHOLD == 0.9
    assert decision_threshold({"decision_threshold_document_type": "0.75"}, "document_type") == 0.75


def test_an_unreadable_threshold_reads_as_default():
    assert decision_threshold({"decision_threshold_correspondent": "1,0"}, "correspondent") == 0.9
    assert decision_threshold({"decision_threshold_correspondent": ""}, "correspondent") == 0.9
    assert decision_threshold({"decision_threshold_correspondent": "0.2"}, "correspondent") == 0.9


def test_questions_default_in_english():
    assert decision_question({}, "correspondent") == "Who sent this document (the correspondent)?"
    assert decision_question({"decision_question_document_type": "Welcher Typ?"}, "document_type") == "Welcher Typ?"


def _decision(**kw):
    base = dict(method="ollama_letters", provider="ollama", model="qwen2.5:7b", index=2, choice="Telekom",
                probability=0.97, mass=0.99, top=[{"name": "Telekom", "p": 0.97}], requests=1,
                rendered="[user] ...", text_chars=120, text_sha256="abcd")
    base.update(kw)
    return Decision(**base)


def test_details_carry_the_whole_decision_without_the_full_request():
    d = decision_details(_decision(), 0.9, "applied")
    assert d["outcome"] == "applied" and d["reason"] is None and d["threshold"] == 0.9
    assert d["choice"] == "Telekom" and d["probability"] == 0.97 and d["method"] == "ollama_letters"
    assert d["request"] == {"text_chars": 120, "text_sha256": "abcd", "rendered": "[user] ..."}
    assert "full" not in d["request"]


def test_the_full_request_is_only_there_when_the_decision_has_it():
    d = decision_details(_decision(full="[user] the text"), 0.9, "applied")
    assert d["request"]["full"] == "[user] the text"


def test_review_marks_the_field_once_and_skips():
    ctx = StepContext(doc_id=1, paperless=None, llm=None, config={}, trigger_tags=set())
    r1 = review(ctx, "correspondent", _decision(probability=0.6), 0.9, "below_threshold")
    r2 = review(ctx, "correspondent", _decision(probability=0.6), 0.9, "below_threshold")
    assert isinstance(r1, StepResult) and r1.skipped and r1.data == {}
    assert r1.details["decision"]["outcome"] == "review" and r1.details["decision"]["reason"] == "below_threshold"
    assert ctx.review_fields == ["correspondent"] and r2.skipped
