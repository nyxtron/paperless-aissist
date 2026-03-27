"""Test modular tag-driven workflows.

Usage:
  python3 test_modular.py [--doc-id N]

Defaults to doc 35. Covers every individual modular tag plus combination scenarios.
OCR steps run but are no-ops when vision is disabled in config.
"""

import asyncio
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))

from app.services.paperless import PaperlessClient
from app.services.processor import DocumentProcessor, MODULAR_TAG_DEFAULTS

PAPERLESS_URL = "http://localhost:8000"
PAPERLESS_TOKEN = "581840c8fa560ac3776172c7837f424cbec09dc9"

parser = argparse.ArgumentParser()
parser.add_argument("--doc-id", type=int, default=35)
args, _ = parser.parse_known_args()
DOC_ID = args.doc_id

# ── Individual step tags ──────────────────────────────────────────────────────
# Each tests exactly one step in isolation.
STEP_TAGS = [
    ("ocr",           MODULAR_TAG_DEFAULTS["modular_tag_ocr"]),
    ("ocr_fix",       MODULAR_TAG_DEFAULTS["modular_tag_ocr_fix"]),
    ("title",         MODULAR_TAG_DEFAULTS["modular_tag_title"]),
    ("correspondent", MODULAR_TAG_DEFAULTS["modular_tag_correspondent"]),
    ("document_type", MODULAR_TAG_DEFAULTS["modular_tag_document_type"]),
    ("tags",          MODULAR_TAG_DEFAULTS["modular_tag_tags"]),
    ("fields",        MODULAR_TAG_DEFAULTS["modular_tag_fields"]),
]

# ── Combination scenarios ─────────────────────────────────────────────────────
# Each entry: (label, [list of tag names to apply together])
COMBO_TAGS = [
    (
        "ai-process (full pipeline)",
        [MODULAR_TAG_DEFAULTS["modular_tag_process"]],
    ),
    (
        "ai-process + ai-ocr + ai-ocr-fix",
        [
            MODULAR_TAG_DEFAULTS["modular_tag_process"],
            MODULAR_TAG_DEFAULTS["modular_tag_ocr"],
            MODULAR_TAG_DEFAULTS["modular_tag_ocr_fix"],
        ],
    ),
]

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


async def ensure_tag(paperless: PaperlessClient, name: str) -> int:
    """Return tag ID, creating it in Paperless if needed."""
    tags = await paperless.get_tags()
    existing = next((t for t in tags if t["name"] == name), None)
    if existing:
        return existing["id"]
    response = await paperless.client.post(
        f"{paperless.base_url}/api/tags/",
        headers=paperless._get_headers(),
        json={"name": name},
    )
    response.raise_for_status()
    created = response.json()
    print(f"  Created tag '{name}' (id={created['id']})")
    return created["id"]


async def get_doc_tags(paperless: PaperlessClient) -> list[int]:
    doc = await paperless.get_document(DOC_ID)
    return list(doc.get("tags", []))


async def set_doc_tags(paperless: PaperlessClient, tag_ids: list[int]):
    await paperless.update_document(DOC_ID, tags=tag_ids)


async def run_test(
    step_name: str,
    trigger_tag_name: str,
    base_tags: list[int],
    paperless: PaperlessClient,
):
    print(f"\n{'=' * 60}")
    print(f"Testing step: {step_name!r}  (tag: {trigger_tag_name!r})")
    print(f"{'=' * 60}")

    trigger_id = await ensure_tag(paperless, trigger_tag_name)

    # Set doc to base_tags + trigger tag
    tags_before = list(base_tags)
    if trigger_id not in tags_before:
        tags_before.append(trigger_id)
    await set_doc_tags(paperless, tags_before)
    print(f"  Tags set to: {tags_before}")

    processor = DocumentProcessor(paperless)
    result = await processor.process_document(DOC_ID)

    if result.get("retryable"):
        print(f"  {YELLOW}SKIP: LLM unavailable — {result.get('error')}{RESET}")
        return

    if not result.get("success"):
        print(f"  {RED}FAIL: {result.get('error')}{RESET}")
        return

    print(f"  {GREEN}SUCCESS{RESET}")
    print(f"  steps run : {result.get('modular_steps')}")
    print(f"  time      : {result.get('processing_time_ms')}ms")
    for s in result.get("steps", []):
        status_col = GREEN if s["status"] in ("completed", "skipped") else RED
        print(
            f"    {status_col}{s['status']:10}{RESET} {s['name']}  ({s['duration_ms']}ms)"
            + (f"  ERR: {s['error']}" if s.get("error") else "")
        )

    # Show resulting tags
    doc_after = await paperless.get_document(DOC_ID)
    all_tags = await paperless.get_tags()
    tag_names = {t["id"]: t["name"] for t in all_tags}
    final_tag_names = [
        tag_names.get(tid, str(tid)) for tid in doc_after.get("tags", [])
    ]
    print(f"  tags after: {final_tag_names}")

    # Check trigger tag was removed
    if trigger_id in doc_after.get("tags", []):
        print(
            f"  {RED}WARNING: trigger tag '{trigger_tag_name}' was NOT removed!{RESET}"
        )
    else:
        print(f"  {GREEN}Trigger tag removed correctly{RESET}")


async def run_combo_test(
    label: str,
    trigger_tag_names: list[str],
    base_tags: list[int],
    paperless: PaperlessClient,
):
    print(f"\n{'=' * 60}")
    print(f"Testing combo: {label!r}")
    print(f"  Tags: {trigger_tag_names}")
    print(f"{'=' * 60}")

    trigger_ids = [await ensure_tag(paperless, name) for name in trigger_tag_names]

    tags_before = list(base_tags)
    for tid in trigger_ids:
        if tid not in tags_before:
            tags_before.append(tid)
    await set_doc_tags(paperless, tags_before)
    print(f"  Tags set to: {tags_before}")

    processor = DocumentProcessor(paperless)
    result = await processor.process_document(DOC_ID)

    if result.get("retryable"):
        print(f"  {YELLOW}SKIP: LLM unavailable — {result.get('error')}{RESET}")
        return

    if not result.get("success"):
        print(f"  {RED}FAIL: {result.get('error')}{RESET}")
        return

    print(f"  {GREEN}SUCCESS{RESET}")
    print(f"  steps run : {result.get('modular_steps')}")
    print(f"  time      : {result.get('processing_time_ms')}ms")
    for s in result.get("steps", []):
        status_col = GREEN if s["status"] in ("completed", "skipped") else RED
        print(
            f"    {status_col}{s['status']:10}{RESET} {s['name']}  ({s['duration_ms']}ms)"
            + (f"  ERR: {s['error']}" if s.get("error") else "")
        )

    doc_after = await paperless.get_document(DOC_ID)
    all_tags = await paperless.get_tags()
    tag_name_map = {t["id"]: t["name"] for t in all_tags}
    final_tag_names = [
        tag_name_map.get(tid, str(tid)) for tid in doc_after.get("tags", [])
    ]
    print(f"  tags after: {final_tag_names}")

    for tid, name in zip(trigger_ids, trigger_tag_names):
        if tid in doc_after.get("tags", []):
            print(f"  {RED}WARNING: trigger tag '{name}' was NOT removed!{RESET}")
        else:
            print(f"  {GREEN}Trigger tag '{name}' removed correctly{RESET}")


async def main():
    paperless = PaperlessClient(PAPERLESS_URL, PAPERLESS_TOKEN)

    # Get original tags to restore after each test
    original_tags = await get_doc_tags(paperless)
    all_tags = await paperless.get_tags()
    tag_names = {t["id"]: t["name"] for t in all_tags}
    print(f"Doc {DOC_ID} original tags: {[tag_names.get(t, t) for t in original_tags]}")

    # Base tags = original minus any existing trigger tags (clean slate)
    base_tags = [
        t
        for t in original_tags
        if tag_names.get(t, "") not in MODULAR_TAG_DEFAULTS.values()
    ]

    print(f"\n{'#' * 60}")
    print("# Individual step tests")
    print(f"{'#' * 60}")
    for step_name, trigger_tag in STEP_TAGS:
        await run_test(step_name, trigger_tag, list(base_tags), paperless)
        await set_doc_tags(paperless, list(base_tags))

    print(f"\n{'#' * 60}")
    print("# Combination tests")
    print(f"{'#' * 60}")
    for label, trigger_tags in COMBO_TAGS:
        await run_combo_test(label, trigger_tags, list(base_tags), paperless)
        await set_doc_tags(paperless, list(base_tags))

    # Restore original tags
    await set_doc_tags(paperless, original_tags)
    print(f"\n{'=' * 60}")
    print(f"Restored original tags: {original_tags}")
    await paperless.close()


if __name__ == "__main__":
    asyncio.run(main())
