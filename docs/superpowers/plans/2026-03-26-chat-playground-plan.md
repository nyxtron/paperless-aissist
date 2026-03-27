# Chat → Playground Feature Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Chat page into a Playground with Paperless search and Preview functionality showing what `ai-process` would change.

**Architecture:** Backend adds search endpoint and preview endpoint that simulates `ai-process` without OCR and without modifying Paperless. Backend resolves IDs to names using Paperless metadata.

**Tech Stack:** FastAPI (backend), React (frontend), axios (API client)

---

## File Map

| File | Change |
|------|--------|
| `backend/app/routers/documents.py` | Add `/search` and `/preview/{doc_id}` endpoints |
| `backend/app/services/paperless.py` | Add `search` param to `list_documents` |
| `backend/app/services/processor.py` | Add `process_document_preview` method |
| `frontend/src/api/client.ts` | Add `searchPaperless` and `getPreview` |
| `frontend/src/pages/ChatPage.tsx` | Add search field, results, preview panel |
| `frontend/src/locales/en.json` | Add chat/search i18n keys |
| `frontend/src/locales/de.json` | Add chat/search i18n keys |

---

## Task 1: Backend – Add Paperless Search

**Files:**
- Modify: `backend/app/services/paperless.py`

- [ ] **Step 1: Add search parameter to list_documents**

Read the current `list_documents` method. Add `search` parameter:

```python
async def list_documents(
    self, tags: Optional[list[int]] = None, search: Optional[str] = None, max_page_limit: int = 100
) -> list[dict]:
    params: dict[str, Any] = {"page_size": 100}
    if tags:
        params["tags__id__all"] = ",".join(map(str, tags))
    if search:
        params["search"] = search
    # ... rest of method unchanged
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/paperless.py
git commit -m "feat: add search parameter to list_documents"
```

---

## Task 2: Backend – Add Search and Preview Endpoints

**Files:**
- Modify: `backend/app/routers/documents.py`

- [ ] **Step 1: Add /search endpoint**

Add after existing imports:
```python
@router.get("/search")
async def search_documents(query: str):
    """Search documents in Paperless by query string."""
    try:
        paperless = await PaperlessClient.from_config()
    except ValueError as e:
        return {"results": [], "error": f"Paperless config error: {str(e)}"}

    try:
        docs = await paperless.list_documents(search=query)
        await paperless.close()

        results = [
            {
                "id": doc.get("id"),
                "title": doc.get("title"),
                "created": doc.get("created"),
            }
            for doc in docs[:5]
        ]
        return {"results": results}
    except Exception as e:
        await paperless.close()
        return {"results": [], "error": str(e)}
```

- [ ] **Step 2: Add /preview/{doc_id} endpoint**

Add after /search:
```python
@router.get("/preview/{doc_id}")
async def get_preview(doc_id: int):
    """Preview what ai-process would do for a document - runs all steps EXCEPT OCR/OCR-fix."""
    try:
        paperless = await PaperlessClient.from_config()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        processor = DocumentProcessor(paperless)
        result = await processor.process_document_preview(doc_id)
        await paperless.close()
        return result
    except Exception as e:
        await paperless.close()
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/documents.py
git commit -m "feat: add search and preview endpoints"
```

---

## Task 3: Backend – Add Preview Method to Processor

**Files:**
- Modify: `backend/app/services/processor.py`

- [ ] **Step 1: Read processor.py to find structure**

- [ ] **Step 2: Add process_document_preview method**

Add after `process_document` method (~line 267):

```python
async def process_document_preview(self, doc_id: int) -> dict[str, Any]:
    """Runs the ai-process pipeline (all steps EXCEPT OCR/OCR-fix) and returns proposed changes without modifying Paperless."""
    config_dict = await self._get_config_dict()
    
    from .steps import (
        TitleStep,
        CorrespondentStep,
        DocumentTypeStep,
        TagsStep,
        FieldsStep,
        ModularTagsStep,
    )
    
    steps = [
        await TitleStep.from_config(config_dict),
        await CorrespondentStep.from_config(config_dict),
        await DocumentTypeStep.from_config(config_dict),
        await TagsStep.from_config(config_dict),
        await FieldsStep.from_config(config_dict),
        await ModularTagsStep.from_config(config_dict),
    ]
    
    try:
        await self.paperless.from_config()
    except ValueError as e:
        return {"success": False, "error": str(e)}
    
    doc = await self.paperless.get_document(doc_id)
    tag_id_to_name = {t["id"]: t["name"] for t in await self.paperless.get_tags()}
    doc_tag_names = {tag_id_to_name.get(tid, "") for tid in doc.get("tags", [])}
    
    from .steps.base import StepContext
    llm = await LLMHandler.from_config(for_vision=False)
    ctx = StepContext(
        doc_id=doc_id,
        paperless=self.paperless,
        llm=llm,
        config=config_dict,
        trigger_tags=doc_tag_names,
        ocr_text=doc.get("content", "").strip() if doc.get("content") else "",
    )
    
    step_records = []
    accumulated_update = {}
    
    # Fetch metadata for resolution
    all_tags = await self.paperless.get_tags()
    all_correspondents = await self.paperless.get_correspondents()
    all_document_types = await self.paperless.get_document_types()
    all_custom_fields = await self.paperless.get_custom_fields()
    
    def add_step(name, status, duration_ms, error=None):
        step_records.append({"name": name, "status": status, "duration_ms": duration_ms, "error": error})
    
    for step_instance in steps:
        if not step_instance.can_handle(doc_tag_names):
            continue
        
        step_start = time.time()
        try:
            result = await step_instance.execute(ctx)
            duration_ms = int((time.time() - step_start) * 1000)
            
            if result.error:
                add_step(step_instance.name, "failed", duration_ms, result.error)
            elif result.data:
                add_step(step_instance.name, "completed", duration_ms)
                # NOTE: update_metadata is NOT called - we don't modify Paperless in preview
                accumulated_update.update(result.data)
            else:
                add_step(step_instance.name, "completed", duration_ms)
        except Exception as step_error:
            duration_ms = int((time.time() - step_start) * 1000)
            add_step(step_instance.name, "failed", duration_ms, str(step_error))
    
    # Resolve IDs to names
    proposed = await self._resolve_proposed_changes(
        accumulated_update, all_tags, all_correspondents, all_document_types, all_custom_fields
    )
    
    return {
        "success": True,
        "document_id": doc_id,
        "steps": step_records,
        "proposed_changes": proposed,
    }
```

- [ ] **Step 3: Add _resolve_proposed_changes method**

Add after `_delete_log` (~line 252):

```python
async def _resolve_proposed_changes(
    self,
    proposed: dict[str, Any],
    all_tags: list[dict],
    all_correspondents: list[dict],
    all_document_types: list[dict],
    all_custom_fields: list[dict],
) -> dict[str, Any]:
    tag_id_to_name = {t["id"]: t["name"] for t in all_tags}
    corr_id_to_name = {c["id"]: c["name"] for c in all_correspondents}
    type_id_to_name = {t["id"]: t["name"] for t in all_document_types}
    cf_id_to_name = {cf["id"]: cf["name"] for cf in all_custom_fields}
    resolved = dict(proposed)

    if "tags" in resolved and isinstance(resolved["tags"], list):
        resolved["tags"] = [
            {"id": tid, "name": tag_id_to_name.get(tid, f"tag:{tid}")}
            for tid in resolved["tags"]
        ]

    if "correspondent" in resolved and isinstance(resolved["correspondent"], int):
        resolved["correspondent"] = {
            "id": resolved["correspondent"],
            "name": corr_id_to_name.get(resolved["correspondent"], f"corr:{resolved['correspondent']}"),
        }

    if "document_type" in resolved and isinstance(resolved["document_type"], int):
        resolved["document_type"] = {
            "id": resolved["document_type"],
            "name": type_id_to_name.get(resolved["document_type"], f"type:{resolved['document_type']}"),
        }

    if "custom_fields" in resolved and isinstance(resolved["custom_fields"], list):
        resolved["custom_fields"] = [
            {
                "id": cf["field"],
                "name": cf_id_to_name.get(cf["field"], f"field:{cf['field']}"),
                "value": cf["value"],
            }
            for cf in resolved["custom_fields"]
        ]

    return resolved
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/processor.py
git commit -m "feat: add process_document_preview method"
```

---

## Task 4: Frontend – Add API Client Functions

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add searchPaperless and getPreview**

Add to `documentsApi`:
```typescript
searchPaperless: (query: string) => api.get('/documents/search', { params: { query } }),
getPreview: (docId: number) => api.get(`/documents/preview/${docId}`),
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add search and preview API functions"
```

---

## Task 5: Frontend – ChatPage Layout

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx`

**Read the current ChatPage.tsx first to understand the existing structure.**

- [ ] **Step 1: Add state variables**

```typescript
const [searchQuery, setSearchQuery] = useState('');
const [searchResults, setSearchResults] = useState<ChatDocument[]>([]);
const [searching, setSearching] = useState(false);
const [previewResult, setPreviewResult] = useState<any>(null);
const [previewing, setPreviewing] = useState(false);
```

- [ ] **Step 2: Add debounced search effect**

```typescript
useEffect(() => {
  if (!searchQuery.trim()) {
    setSearchResults([]);
    return;
  }
  
  const timer = setTimeout(async () => {
    setSearching(true);
    try {
      const res = await documentsApi.searchPaperless(searchQuery);
      setSearchResults(res.data.results || []);
    } catch (err) {
      console.error('Search failed:', err);
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }, 300);

  return () => clearTimeout(timer);
}, [searchQuery]);
```

- [ ] **Step 3: Add handlePreview function**

```typescript
const handlePreview = async () => {
  if (!selectedDoc) return;
  setPreviewing(true);
  try {
    const res = await documentsApi.getPreview(selectedDoc);
    setPreviewResult(res.data);
  } catch (err: any) {
    toast.error(err.response?.data?.detail || err.message);
  } finally {
    setPreviewing(false);
  }
};
```

- [ ] **Step 4: Add search input to left panel**

Add at top of document list panel:
```tsx
<div className="p-3 border-b bg-gray-50">
  <input
    type="text"
    value={searchQuery}
    onChange={(e) => setSearchQuery(e.target.value)}
    placeholder={t('chat.searchPlaceholder')}
    className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
  />
</div>
```

- [ ] **Step 5: Show search results or original list**

Replace the document list with conditional rendering:
- If `searchQuery.trim()` is non-empty → show `searchResults` (max 5)
- Else → show original `documents` list

When showing search results:
```tsx
{searchResults.length === 0 ? (
  <div className="p-4 text-sm text-gray-500 text-center">
    {searching ? t('chat.searching') : t('chat.noResults')}
  </div>
) : (
  searchResults.slice(0, 5).map(doc => (
    <button
      key={doc.id}
      onClick={() => selectDocument(doc.id)}
      className={`w-full text-left p-3 border-b hover:bg-gray-50 ${
        selectedDoc === doc.id ? 'bg-blue-50 border-l-4 border-l-blue-500' : ''
      }`}
    >
      <div className="flex items-start gap-2">
        <FileText size={16} className="text-gray-400 mt-0.5 flex-shrink-0" />
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-900 truncate">
            {doc.title || `Document #${doc.id}`}
          </p>
          <p className="text-xs text-gray-500">
            {new Date(doc.created).toLocaleDateString()}
          </p>
        </div>
      </div>
    </button>
  ))
)}
```

Note: `selectDocument(docId)` already exists in ChatPage.tsx.

- [ ] **Step 6: Add Preview panel on right side**

Add conditionally when `selectedDoc || previewResult`:
```tsx
<div className="w-96 bg-white rounded-lg shadow overflow-hidden flex flex-col">
  <div className="p-4 border-b bg-gray-50 flex justify-between items-center">
    <h3 className="font-semibold">{t('chat.previewTitle')}</h3>
    {previewResult ? (
      <button
        onClick={() => setPreviewResult(null)}
        className="text-sm text-gray-500 hover:text-gray-700"
      >
        {t('common.close')}
      </button>
    ) : (
      <button
        onClick={handlePreview}
        disabled={previewing || !selectedDoc}
        className="px-3 py-1 bg-green-600 text-white text-sm rounded hover:bg-green-700 disabled:opacity-50"
      >
        {previewing ? t('chat.previewing') : t('chat.preview')}
      </button>
    )}
  </div>
  <div className="p-4 overflow-y-auto flex-1">
    {!previewResult ? (
      <p className="text-sm text-gray-500">{t('chat.previewHint')}</p>
    ) : previewResult.success ? (
      <div className="space-y-2">
        <p className="text-sm text-green-700">{t('chat.previewSuccess')}</p>
        {previewResult.steps?.map((step: any, idx: number) => (
          <div key={idx} className="flex justify-between text-sm">
            <span>{step.name}</span>
            <span className="text-gray-500">{step.status}</span>
          </div>
        ))}
        {previewResult.proposed_changes && Object.keys(previewResult.proposed_changes).length > 0 && (
          <div className="mt-4 pt-4 border-t">
            <h4 className="text-sm font-medium mb-2">{t('chat.proposedChanges')}</h4>
            {/* Backend resolves IDs to names - display directly */}
            {previewResult.proposed_changes.title && (
              <p className="text-sm">Title: {previewResult.proposed_changes.title}</p>
            )}
            {previewResult.proposed_changes.correspondent && (
              <p className="text-sm">Correspondent: {previewResult.proposed_changes.correspondent.name}</p>
            )}
            {previewResult.proposed_changes.document_type && (
              <p className="text-sm">Type: {previewResult.proposed_changes.document_type.name}</p>
            )}
            {previewResult.proposed_changes.tags && (
              <p className="text-sm">Tags: {previewResult.proposed_changes.tags.map((t: any) => t.name).join(', ')}</p>
            )}
            {previewResult.proposed_changes.custom_fields && (
              <p className="text-sm">Fields: {previewResult.proposed_changes.custom_fields.map((f: any) => `${f.name}: ${f.value}`).join(', ')}</p>
            )}
          </div>
        )}
      </div>
    ) : (
      <p className="text-sm text-red-700">{previewResult.error}</p>
    )}
  </div>
</div>
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ChatPage.tsx
git commit -m "feat: add search and preview to chat page"
```

---

## Task 6: i18n Keys

**Files:**
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`

- [ ] **Step 1: Add English keys**

Add to "chat" section:
```json
"searchPlaceholder": "Search Paperless...",
"searching": "Searching...",
"noResults": "No documents found",
"preview": "Preview",
"previewing": "Previewing...",
"previewTitle": "Proposed Changes",
"previewSuccess": "Preview complete",
"proposedChanges": "Proposed Changes",
"previewHint": "Click Preview to see what ai-process would change"
```

Add to "common" section:
```json
"close": "Close"
```

- [ ] **Step 2: Add German keys**

```json
"searchPlaceholder": "Paperless durchsuchen...",
"searching": "Suche läuft...",
"noResults": "Keine Dokumente gefunden",
"preview": "Vorschau",
"previewing": "Vorschau läuft...",
"previewTitle": "Vorgeschlagene Änderungen",
"previewSuccess": "Vorschau abgeschlossen",
"proposedChanges": "Vorgeschlagene Änderungen",
"previewHint": "Klicke Vorschau um zu sehen was ai-process ändern würde"
```

Add to "common" section:
```json
"close": "Schließen"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/locales/en.json frontend/src/locales/de.json
git commit -m "i18n: add search and preview labels"
```

---

## Task 7: Verify End-to-End

- [ ] **Step 1: Start backend**

```bash
cd backend && DATA_DIR=../data python3 -m uvicorn app.main:app --reload --port 8002
```

- [ ] **Step 2: Start frontend**

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: Test search**

Navigate to `/chat`, type in search field, verify results appear.

- [ ] **Step 4: Test preview**

Select a document, click Preview, verify proposed changes appear in right panel.

- [ ] **Step 5: Verify no changes to Paperless**

Check that clicking Preview does NOT update the document in Paperless.

- [ ] **Step 6: Commit final**

```bash
git status
git commit -m "feat: complete chat playground with search and preview"
```
