import logging
from typing import Any

from .base import AbstractStep, StepContext, StepResult

logger = logging.getLogger(__name__)


class FieldsStep(AbstractStep):
    name = "fields"

    def __init__(self, config):
        self.config = config

    @classmethod
    async def from_config(cls, config):
        return cls(config)

    def can_handle(self, tags: set[str]) -> bool:
        process_tag = self.config.get("modular_tag_process") or "ai-process"
        fields_tag = self.config.get("modular_tag_fields") or "ai-fields"
        return process_tag in tags or fields_tag in tags

    async def execute(self, ctx: StepContext) -> StepResult:
        from ...database import get_session
        from ...models import Prompt
        from sqlmodel import select

        text = ctx.ocr_text
        if not text:
            doc = await ctx.paperless.get_document(ctx.doc_id)
            text = doc.get("content", "").strip() if doc.get("content") else ""

        if not text:
            return StepResult(data={}, error="No content available")

        combined_fields: dict[str, str] = {}

        with get_session() as session:
            stmt = select(Prompt).where(
                Prompt.prompt_type == "extract", Prompt.is_active == True
            )
            extract_prompt = session.exec(stmt).first()
            extract_prompt_data = (
                {
                    "system_prompt": extract_prompt.system_prompt,
                    "user_template": extract_prompt.user_template,
                }
                if extract_prompt
                else None
            )

        if extract_prompt_data:
            try:
                user_msg = extract_prompt_data["user_template"].replace(
                    "{content}", text[:10000]
                )
                extract_result = await ctx.llm.complete(
                    system_prompt=extract_prompt_data["system_prompt"],
                    user_prompt=user_msg,
                    json_mode=True,
                )

                if extract_result and isinstance(extract_result, dict):
                    combined_fields.update(
                        self._extract_fields_from_result(extract_result)
                    )
            except Exception as e:
                logger.warning(
                    f"FieldsStep: extract prompt failed for doc {ctx.doc_id}: {e}"
                )

        detected_type = ctx.detected_type
        if not detected_type:
            doc = await ctx.paperless.get_document(ctx.doc_id)
            if doc.get("document_type"):
                doc_types = await ctx.paperless.get_document_types()
                detected_type = next(
                    (
                        dt["name"]
                        for dt in doc_types
                        if dt["id"] == doc.get("document_type")
                    ),
                    None,
                )

        type_specific_prompt_data = None
        if detected_type:
            with get_session() as session:
                stmt = select(Prompt).where(
                    Prompt.prompt_type == "type_specific",
                    Prompt.document_type_filter == detected_type,
                    Prompt.is_active == True,
                )
                type_specific_prompt = session.exec(stmt).first()
                if type_specific_prompt:
                    type_specific_prompt_data = {
                        "system_prompt": type_specific_prompt.system_prompt,
                        "user_template": type_specific_prompt.user_template,
                    }

        if type_specific_prompt_data:
            try:
                user_msg = type_specific_prompt_data["user_template"].replace(
                    "{content}", text[:10000]
                )
                type_result = await ctx.llm.complete(
                    system_prompt=type_specific_prompt_data["system_prompt"],
                    user_prompt=user_msg,
                    json_mode=True,
                )
                if type_result and isinstance(type_result, dict):
                    combined_fields.update(
                        self._extract_fields_from_result(type_result)
                    )
            except Exception as e:
                logger.warning(
                    f"FieldsStep: type_specific prompt failed for doc {ctx.doc_id}: {e}"
                )

        if not combined_fields:
            return StepResult(data={}, error=None)

        doc = await ctx.paperless.get_document(ctx.doc_id)
        paperless_custom_fields = await ctx.paperless.get_custom_fields()
        field_name_to_id = {
            cf["name"].lower(): cf["id"] for cf in paperless_custom_fields
        }

        existing_cf = {cf["field"]: cf["value"] for cf in doc.get("custom_fields", [])}
        for field_name, field_value in combined_fields.items():
            field_id = field_name_to_id.get(field_name)
            if field_id and field_value:
                existing_cf[field_id] = field_value

        converted_fields = [
            {"field": fid, "value": val} for fid, val in existing_cf.items()
        ]

        if converted_fields:
            logger.debug(
                f"FieldsStep: extracted {len(converted_fields)} fields for doc {ctx.doc_id}"
            )
            return StepResult(data={"custom_fields": converted_fields}, error=None)

        return StepResult(data={}, error=None)

    async def update_metadata(self, ctx: StepContext, result: StepResult) -> None:
        pass

    @staticmethod
    def _extract_fields_from_result(result: dict) -> dict[str, str]:
        fields: dict[str, str] = {}
        items = []

        if "custom_fields" in result:
            items = result["custom_fields"]
        elif "extract" in result:
            for k, v in result["extract"].items():
                if v:
                    fields[k.lower()] = v
            return fields
        elif "field" in result and "value" in result:
            items = [result]

        for key, value in result.items():
            if (
                key not in ("custom_fields", "extract")
                and isinstance(value, str)
                and value
            ):
                fields[key.lower()] = value

        for item in items:
            if isinstance(item, dict) and item.get("field") and item.get("value"):
                fields[str(item["field"]).lower()] = item["value"]

        return fields
