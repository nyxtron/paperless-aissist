# Refactoring Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor Paperless-AIssist: decompose processor.py, add input validation, fix CORS/pagination, split ConfigPanel, replace alert() with toasts.

**Architecture:** 5 independent refactoring steps executed in sequence. Each step is self-contained with no external API changes. Backend first, then frontend.

**Tech Stack:** Python/FastAPI backend, React/TypeScript frontend, SQLModel, APScheduler, httpx, sonner

---

## File Map

### New Files (Backend)
- `backend/app/services/steps/__init__.py`
- `backend/app/services/steps/base.py`
- `backend/app/services/steps/ocr_step.py`
- `backend/app/services/steps/ocr_fix_step.py`
- `backend/app/services/steps/title_step.py`
- `backend/app/services/steps/correspondent_step.py`
- `backend/app/services/steps/document_type_step.py`
- `backend/app/services/steps/tags_step.py`
- `backend/app/services/steps/fields_step.py`
- `backend/app/services/steps/swap_tags_step.py`

### Modified Files (Backend)
- `backend/app/services/processor.py` – refactor to use Step classes
- `backend/app/services/vision.py` – extract PDF-to-image logic, consumed by ocr_step
- `backend/app/services/llm_handler.py` – no changes, consumed by steps
- `backend/app/main.py` – CORS from config
- `backend/app/routers/config.py` – add ConfigUpdate Pydantic model
- `backend/app/routers/documents.py` – add ProcessRequest Pydantic model
- `backend/app/routers/scheduler.py` – add SchedulerUpdate Pydantic model

### Modified Files (Frontend)
- `frontend/src/App.tsx` – add Toaster
- `frontend/src/components/ConfigPanel.tsx` – split into sub-components
- `frontend/src/components/ConfigSectionPaperless.tsx` – new
- `frontend/src/components/ConfigSectionLLM.tsx` – new
- `frontend/src/components/ConfigSectionVision.tsx` – new
- `frontend/src/components/ConfigSectionScheduler.tsx` – new
- `frontend/src/components/ConfigSectionTags.tsx` – new
- `frontend/src/components/ConfigSectionAdvanced.tsx` – new
- `frontend/src/components/ProcessingPanel.tsx` – alert → toast
- `frontend/src/components/Dashboard.tsx` – alert → toast
- `frontend/src/pages/ChatPage.tsx` – alert → toast

---

## Step 1: processor.py Strategy Pattern Decomposition

**Files:**
- Create: `backend/app/services/steps/` (directory + all step files)
- Modify: `backend/app/services/processor.py`
- Modify: `backend/app/services/vision.py`

### Task 1.1: Create Step Base Classes

- [ ] **Step 1: Create `backend/app/services/steps/__init__.py`**

```python
from .base import AbstractStep, StepContext, StepResult
from .ocr_step import OCRStep
from .ocr_fix_step import OCRFixStep
from .title_step import TitleStep
from .correspondent_step import CorrespondentStep
from .document_type_step import DocumentTypeStep
from .tags_step import TagsStep
from .fields_step import FieldsStep
from .swap_tags_step import SwapTagsStep

__all__ = [
    "AbstractStep", "StepContext", "StepResult",
    "OCRStep", "OCRFixStep", "TitleStep",
    "CorrespondentStep", "DocumentTypeStep",
    "TagsStep", "FieldsStep", "SwapTagsStep",
]
```

- [ ] **Step 2: Create `backend/app/services/steps/base.py`**

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.paperless import PaperlessClient
    from app.services.llm_handler import LLMHandler
    from app.models import Config

@dataclass
class StepResult:
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

@dataclass
class StepContext:
    doc_id: int
    paperless: PaperlessClient
    llm: LLMHandler
    config: Config
    trigger_tags: set[str]

    async def get_document(self):
        return await self.paperless.get_document(self.doc_id)

class AbstractStep(ABC):
    name: str

    @abstractmethod
    def can_handle(self, tags: set[str]) -> bool:
        pass

    @abstractmethod
    async def execute(self, ctx: StepContext) -> StepResult:
        pass

    async def update_metadata(self, ctx: StepContext, result: StepResult) -> None:
        pass

    def _match_tag(self, doc_tags: set[str], target: str) -> bool:
        return target in doc_tags
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/steps/
git commit -m "refactor: add Step base classes and directory structure"
```

### Task 1.2: Extract Each Step

- [ ] **Step 1: Create `backend/app/services/steps/ocr_step.py`**

```python
from .base import AbstractStep, StepContext, StepResult
# OCR step uses vision.py logic - extract_pdf_pages and vision_complete
# Read current vision.py to understand what to call
```

- [ ] **Step 2: Create `backend/app/services/steps/ocr_fix_step.py`**
- [ ] **Step 3: Create `backend/app/services/steps/title_step.py`**
- [ ] **Step 4: Create `backend/app/services/steps/correspondent_step.py`**
- [ ] **Step 5: Create `backend/app/services/steps/document_type_step.py`**
- [ ] **Step 6: Create `backend/app/services/steps/tags_step.py`**
- [ ] **Step 7: Create `backend/app/services/steps/fields_step.py`**
- [ ] **Step 8: Create `backend/app/services/steps/swap_tags_step.py`**

### Task 1.3: Refactor processor.py to Use Steps

- [ ] **Step 1: Read current `backend/app/services/processor.py` fully**
- [ ] **Step 2: Replace DocumentProcessor to use Step classes**
- [ ] **Step 3: Verify existing test_modular.py still passes**

Run: `cd backend && DATA_DIR=../data python3 test_modular.py`

### Task 1.4: Commit Step 1

```bash
git add backend/app/services/processor.py backend/app/services/steps/
git commit -m "refactor: decompose processor.py into Step strategy classes"
```

---

## Step 2: Input Validation on Routers

**Files:**
- Modify: `backend/app/routers/config.py`
- Modify: `backend/app/routers/documents.py`
- Modify: `backend/app/routers/scheduler.py`

### Task 2.1: Add Pydantic Models to Routers

- [ ] **Step 1: Read `backend/app/routers/config.py` fully**
- [ ] **Step 2: Add ConfigUpdate Pydantic model and apply to POST /config**

```python
from pydantic import BaseModel

class ConfigUpdate(BaseModel):
    key: str
    value: str
```

- [ ] **Step 3: Read `backend/app/routers/documents.py` fully**
- [ ] **Step 4: Add ProcessRequest Pydantic model and apply to POST /process**
- [ ] **Step 5: Read `backend/app/routers/scheduler.py` fully**
- [ ] **Step 6: Add SchedulerUpdate Pydantic model and apply to PUT /scheduler**

### Task 2.2: Test Validation

- [ ] **Step 1: Send malformed request to POST /config (e.g., missing 'key')**

Expected: 422 response

- [ ] **Step 2: Commit**

```bash
git add backend/app/routers/config.py backend/app/routers/documents.py backend/app/routers/scheduler.py
git commit -m "refactor: add Pydantic validation to router endpoints"
```

---

## Step 3: CORS Restriction + Pagination Limits

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/paperless.py`

### Task 3.1: CORS from Config

- [ ] **Step 1: Read `backend/app/main.py` fully**
- [ ] **Step 2: Change CORS to read from config**

```python
origins_str = config.get("allowed_origins", "*")
origins = [o.strip() for o in origins_str.split(",")] if origins_str != "*" else ["*"]
```

### Task 3.2: Pagination Limits

- [ ] **Step 1: Read `backend/app/services/paperless.py` fully**
- [ ] **Step 2: Add max_page_limit parameter to list_documents and all list methods**
- [ ] **Step 3: Read from config, default to 100**
- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py backend/app/services/paperless.py
git commit -m "fix: restrict CORS via config and add pagination limits"
```

---

## Step 4: ConfigPanel.tsx Decomposition

**Files:**
- Create: `frontend/src/components/ConfigSection*.tsx` (6 files)
- Modify: `frontend/src/components/ConfigPanel.tsx`

### Task 4.1: Create ConfigSection Components

- [ ] **Step 1: Read `frontend/src/components/ConfigPanel.tsx` fully**
- [ ] **Step 2: Create `frontend/src/components/ConfigSectionPaperless.tsx`**
- [ ] **Step 3: Create `frontend/src/components/ConfigSectionLLM.tsx`**
- [ ] **Step 4: Create `frontend/src/components/ConfigSectionVision.tsx`**
- [ ] **Step 5: Create `frontend/src/components/ConfigSectionScheduler.tsx`**
- [ ] **Step 6: Create `frontend/src/components/ConfigSectionTags.tsx`**
- [ ] **Step 7: Create `frontend/src/components/ConfigSectionAdvanced.tsx`**

### Task 4.2: Refactor ConfigPanel.tsx

- [ ] **Step 1: Refactor ConfigPanel.tsx to import and compose sections**
- [ ] **Step 2: Test all sections render and save correctly in browser**
- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ConfigPanel.tsx frontend/src/components/ConfigSection*.tsx
git commit -m "refactor: decompose ConfigPanel into focused section components"
```

---

## Step 5: Toast Notifications

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/ConfigPanel.tsx` (remove alerts)
- Modify: `frontend/src/components/ProcessingPanel.tsx`
- Modify: `frontend/src/components/Dashboard.tsx`
- Modify: `frontend/src/pages/ChatPage.tsx`

### Task 5.1: Install sonner

- [ ] **Step 1: Install `sonner`**

Run: `cd frontend && npm install sonner`

### Task 5.2: Add Toaster to App.tsx

- [ ] **Step 1: Read `frontend/src/App.tsx`**
- [ ] **Step 2: Import and add `<Toaster />`**

### Task 5.3: Migrate alert() Calls

- [ ] **Step 1: Find all alert() calls in frontend/src/**

Run: `grep -rn "alert(" frontend/src/`

- [ ] **Step 2: Replace with toast in ConfigPanel.tsx**
- [ ] **Step 3: Replace with toast in ProcessingPanel.tsx**
- [ ] **Step 4: Replace with toast in Dashboard.tsx**
- [ ] **Step 5: Replace with toast in ChatPage.tsx**
- [ ] **Step 6: Test all toasts appear correctly in browser**
- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/ConfigPanel.tsx \
  frontend/src/components/ProcessingPanel.tsx frontend/src/components/Dashboard.tsx \
  frontend/src/pages/ChatPage.tsx
git commit -m "refactor: replace alert() with sonner toasts"
```

---

## Final Verification

After all 5 steps:

1. Run backend tests: `cd backend && DATA_DIR=../data python3 test_modular.py`
2. TypeScript check: `cd frontend && npx tsc --noEmit`
3. Manual UI test: navigate all pages in browser at http://localhost:5173
4. Verify no `alert()` remaining: `grep -rn "alert(" frontend/src/`

---

## Open Questions for Implementer

- vision.py PDF-to-image logic: confirm it can be used directly by ocr_step or needs extraction
- Each step's `can_handle` logic: verify tag matching against MODULAR_TAG_DEFAULTS
- ConfigPanel sections: confirm which fields belong to which section by reading existing ConfigPanel.tsx
