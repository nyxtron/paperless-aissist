"""The decision prompts are ordinary prompt rows: seeded, listed with their
own placeholders, and saved with a warning when a placeholder is missing."""

from sqlmodel import select

from app.database import get_session
from app.models import Prompt

DECISION_VARS = ["{content}", "{question}", "{options}"]


def test_the_two_prompts_are_seeded(client):
    with get_session() as session:
        rows = session.exec(select(Prompt).where(Prompt.prompt_type.in_(["decision_correspondent", "decision_document_type"]))).all()
        by_type = {r.prompt_type: r for r in rows}
        assert set(by_type) == {"decision_correspondent", "decision_document_type"}
        for row in by_type.values():
            assert row.is_active and all(v in row.user_template for v in DECISION_VARS)
            assert "letter" in row.system_prompt.lower()


def test_the_templates_list_the_types_with_their_own_variables(client):
    body = client.get("/api/prompts/templates").json()
    types = {t["value"]: t for t in body["types"]}
    assert [v["name"] for v in types["decision_correspondent"]["variables"]] == DECISION_VARS
    assert [v["name"] for v in types["decision_document_type"]["variables"]] == DECISION_VARS
    assert "variables" not in types["correspondent"]
    assert {"name": "{options}", "description": "The lettered options, last one \"None of these\""} in types["decision_correspondent"]["variables"]


def test_saving_without_a_placeholder_warns_but_saves(client):
    r = client.post("/api/prompts", json={"name": "dec-test", "prompt_type": "decision_correspondent",
                                          "system_prompt": "s", "user_template": "{content} only", "is_active": False})
    assert r.status_code == 200
    assert r.json()["warning"] == {"code": "missing_placeholders", "missing": ["{question}", "{options}"]}
    pid = r.json()["id"]
    r = client.put(f"/api/prompts/{pid}", json={"user_template": "{content} {question} {options}"})
    assert "warning" not in r.json()
    r = client.put(f"/api/prompts/{pid}", json={"system_prompt": "{options} moved here", "user_template": "{content} {question}"})
    assert r.json()["warning"]["missing"] == ["{options}"]
    client.delete(f"/api/prompts/{pid}")


def test_other_types_never_warn(client):
    r = client.post("/api/prompts", json={"name": "title-test", "prompt_type": "title",
                                          "system_prompt": "s", "user_template": "no placeholders", "is_active": False})
    assert "warning" not in r.json()
    client.delete(f"/api/prompts/{r.json()['id']}")
