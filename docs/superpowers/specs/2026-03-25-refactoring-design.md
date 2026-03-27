# Refactoring Design – Paperless-AIssist

**Date:** 2026-03-25
**Status:** Draft

## Overview

Comprehensive refactoring of Paperless-AIssist to improve code quality, maintainability, and production readiness. Five independent improvements, executed in sequence (Backend → Frontend).

**Order:** processor.py → Input Validation → CORS + Pagination → ConfigPanel → Toast Notifications

---

## Step 1: processor.py – Strategy Pattern Decomposition

### Problem

`services/processor.py` is 1284 lines, handling OCR, classification, title generation, tag management, and logging in a single God Class. Duplicate code exists between legacy and modular pipelines. Three identical tag-matching loops. Two copies of `_extract_fields_from_result`.

### Solution

Introduce a `Step` base class and extract each processing stage into its own handler class.

#### New Structure

```
services/
├── processor.py           # DocumentProcessor orchestrator (~200 lines)
├── steps/
│   ├── __init__.py
│   ├── base.py           # AbstractStep, StepResult dataclass
│   ├── ocr_step.py        # Vision OCR (extracted from vision.py)
│   ├── ocr_fix_step.py   # OCR error correction
│   ├── title_step.py     # Title generation
│   ├── correspondent_step.py
│   ├── document_type_step.py
│   ├── tags_step.py
│   ├── fields_step.py    # Custom field extraction
│   └── swap_tags_step.py # process_tag → processed_tag swap
```

#### Step Interface

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class StepResult:
    data: dict[str, Any]
    error: str | None = None

@dataclass
class StepContext:
    doc_id: int
    paperless: PaperlessClient
    llm: LLMHandler
    config: Config
    trigger_tags: set[str]

class AbstractStep(ABC):
    name: str

    def can_handle(self, tags: set[str]) -> bool:
        """Check if this step should run given the document's current tags."""

    async def execute(self, ctx: StepContext) -> StepResult:
        """Execute the step. Returns extracted data."""

    async def update_metadata(self, ctx: StepContext, result: StepResult) -> None:
        """Apply step results to Paperless document."""
```

#### Relationship Between Steps

- `ocr_step.py` (Vision OCR): Uses vision model to extract text from document images/PDFs
- `ocr_fix_step.py` (OCR Fix): Takes OCR output and corrects errors using the main LLM
- `vision.py` is refactored to be consumed by `ocr_step.py` (its PDF-to-image logic is reused)
- `ocr_fix_step` runs after `ocr_step` when `ai-ocr-fix` tag is present

#### DocumentProcessor Changes

`DocumentProcessor` becomes a thin orchestrator:

```python
class DocumentProcessor:
    def __init__(self, config: Config):
        self.steps = self._build_steps(config)

    def _build_steps(self, config: Config) -> list[AbstractStep]:
        return [
            OCRStep.from_config(config),
            OCRFixStep.from_config(config),
            TitleStep.from_config(config),
            CorrespondentStep.from_config(config),
            DocumentTypeStep.from_config(config),
            TagsStep.from_config(config),
            FieldsStep.from_config(config),
            SwapTagsStep.from_config(config),
        ]

    async def process_document(self, doc_id: int, trigger_tags: set[str]) -> StepResult:
        ctx = StepContext(doc_id=doc_id, ...)
        selected_steps = [s for s in self.steps if s.can_handle(trigger_tags)]
        for step in selected_steps:
            result = await step.execute(ctx)
            await step.update_metadata(ctx, result)
        return StepResult(data={...})
```

#### What Stays the Same

- External API: `POST /api/documents/process` and `POST /api/documents/process-modular` behave identically
- Database schema unchanged
- Frontend unchanged
- Paperless API calls unchanged

#### What Changes

- Duplicate tag-matching logic → `BaseStep._match_tag()`
- Duplicate field extraction → `FieldsStep._extract_fields_from_result()` in base
- Legacy and modular pipelines share the same Step classes

---

## Step 2: Input Validation on Routers

### Problem

Router endpoints accept raw dicts with no validation. Malformed requests cause runtime errors.

### Solution

Add Pydantic models for request bodies on all POST/PUT endpoints.

#### Affected Routers

| Router | New Models |
|--------|-----------|
| `routers/config.py` | `ConfigUpdate(key: str, value: str)` |
| `routers/documents.py` | `ProcessRequest(document_id: int, force: bool = False)` |
| `routers/scheduler.py` | `SchedulerUpdate(enabled: bool, interval: int)` |

#### Implementation

```python
# routers/config.py
from pydantic import BaseModel

class ConfigUpdate(BaseModel):
    key: str
    value: str

@router.post("/config")
async def update_config(data: ConfigUpdate):
    ...
```

Invalid requests return `422 Unprocessable Entity` automatically from FastAPI.

---

## Step 3: CORS Restriction + Pagination Limits

### Problem

`allow_origins=["*"]` is too permissive for production. `list_documents()` fetches all pages with no limit.

### Solution

#### CORS

Add `allowed_origins` config key (comma-separated string). Default to `*` for backward compatibility.

```python
# main.py
origins = [o.strip() for o in config.get("allowed_origins", "*").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    ...
)
```

#### Pagination

Add `max_page_limit` config key (int, default 100). Enforce on all list endpoints.

```python
async def list_documents(paperless: PaperlessClient, max_page_limit: int = 100):
    for page in range(max_page_limit):
        ...
```

---

## Step 4: ConfigPanel.tsx Decomposition

### Problem

`components/ConfigPanel.tsx` is 746 lines, mixing paperless settings, LLM settings, vision, scheduler, tags, and advanced into one file.

### Solution

Split into focused sub-components.

```
components/
├── ConfigPanel.tsx               # Container, layout (~100 lines)
├── ConfigSectionPaperless.tsx   # Paperless URL + token
├── ConfigSectionLLM.tsx        # LLM provider, model, api_base, api_key
├── ConfigSectionVision.tsx      # Vision model, enable_vision, ocr_post_process
├── ConfigSectionScheduler.tsx   # Scheduler enabled, interval
├── ConfigSectionTags.tsx        # Process tag, processed tag, modular tags
└── ConfigSectionAdvanced.tsx    # Auth, CORS origins, pagination limit
```

#### Props Interface

```typescript
interface ConfigSectionProps {
  config: Record<string, string>;
  onSave: (key: string, value: string) => Promise<void>;
  onTest?: (key: string) => Promise<boolean>;
}
```

#### ConfigPanel.tsx

```tsx
export function ConfigPanel({ config, onSave }: ConfigSectionProps) {
  return (
    <div className="space-y-6">
      <ConfigSectionPaperless config={config} onSave={onSave} />
      <ConfigSectionLLM config={config} onSave={onSave} />
      <ConfigSectionVision config={config} onSave={onSave} />
      <ConfigSectionScheduler config={config} onSave={onSave} />
      <ConfigSectionTags config={config} onSave={onSave} />
      <ConfigSectionAdvanced config={config} onSave={onSave} />
    </div>
  );
}
```

---

## Step 5: Toast Notifications

### Problem

`alert()` is blocking, synchronous, and ugly.

### Solution

Install `sonner` (lightweight, minimal footprint).

```bash
cd frontend && npm install sonner
```

#### Changes

- Add `<Toaster />` to `App.tsx`
- Replace all `alert()` calls with `toast.success()`, `toast.error()`, etc.

#### Example Migrations

```tsx
// Before
alert('Document processed!');

// After
import { toast } from 'sonner';
toast.success('Document processed!');
```

#### Affected Files

- `ConfigPanel.tsx` – test result feedback
- `ProcessingPanel.tsx` – process result feedback
- `Dashboard.tsx` – reset confirmation
- `ChatPage.tsx` – error feedback

---

## Dependencies

| Change | New Dependency | Backend Dev | Frontend Dev |
|--------|---------------|-------------|-------------|
| Step 1 | None | None | None |
| Step 2 | None | None | None |
| Step 3 | None | None | None |
| Step 4 | None | None | None |
| Step 5 | `sonner` | None | `npm install sonner` |

---

## Backward Compatibility

All changes are internal refactoring with no external API changes:

- Step 1: Behavior identical, only internal structure changes
- Step 2: Invalid inputs now return 422 instead of 500 – improvement
- Step 3: Defaults preserve existing behavior
- Step 4: Props API is internal
- Step 5: UI feedback only

---

## Testing Strategy

1. **Step 1**: Run `python test_modular.py` against real Paperless instance after refactor
2. **Step 2**: Manual API testing with invalid payloads (should get 422)
3. **Step 3**: Manual CORS test with non-whitelisted origin
4. **Step 4**: Manual UI test – navigate all config sections, save values
5. **Step 5**: Manual UI test – trigger all actions that show feedback

---

## Sequence

1. `services/steps/` – create directory, implement base + all steps
2. Refactor `processor.py` to use new Step classes
3. Add Pydantic models to routers
4. Update CORS + pagination limits
5. Split `ConfigPanel.tsx` into sub-components
6. Add `sonner`, migrate all `alert()` calls
