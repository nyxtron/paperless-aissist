# Chat → Playground Feature (Preview Mode)

**Date:** 2026-03-26
**Status:** Approved

## Problem

Currently, "Manual Process" in the ProcessingPanel immediately applies all AI-generated changes to Paperless. Users have no way to preview proposed changes before they are committed.

## Solution

Preview simulates what `ai-process` would do - runs all steps (title, correspondent, document_type, tags, fields, modular_tags) but WITHOUT committing to Paperless. OCR steps are NOT run in preview.

### Behavior

- Preview runs the FULL `ai-process` pipeline (all modular steps EXCEPT OCR/OCR-fix)
- Shows proposed changes in the UI with resolved names (not IDs)
- Does NOT modify the document in Paperless

### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  [Chat Page]                                                     │
│  ┌─────────────────────────┐  ┌──────────────────────────────┐ │
│  │  [🔍 Search Paperless]  │  │   Preview Button             │ │
│  │  ────────────────────  │  │   (only when doc loaded)    │ │
│  │  📄 Result 1 - Title   │  │                              │ │
│  │  📄 Result 2 - Title   │  │   Proposed Changes Panel     │ │
│  │  ...                   │  │   (Steps + Updates)         │ │
│  │  ────────────────────  │  │                              │ │
│  │  [Document Content]     │  │                              │ │
│  │  [Message input]       │  │                              │ │
│  └─────────────────────────┘  └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Search

- **Input:** Debounced (300ms) text field
- **API:** `GET /api/documents/search?query={text}` (Paperless native search)
- **Results:** Max 5 documents, title + created date
- **Interaction:** Click result → load document via existing `selectDocument()`

### Preview

- **Button:** "Preview" (only when document loaded)
- **API:** `GET /api/documents/preview/{doc_id}` (new dedicated endpoint)
- **Response:** Steps + proposed_changes with resolved names
- **Display:** Right panel with Steps list + proposed changes with names

### ID Resolution

Backend resolves IDs to names using metadata already fetched from Paperless (tags, correspondents, document_types, custom_fields).

## API Design

#### `GET /api/documents/search?query={text}`
Searches Paperless for documents matching the query.

**Response:**
```json
{
  "results": [
    {"id": 42, "title": "Invoice", "created": "2026-03-01"},
    ...
  ]
}
```

#### `GET /api/documents/preview/{doc_id}`
Runs `ai-process` simulation (all steps EXCEPT OCR/OCR-fix) and returns proposed changes with resolved names.

**Response:**
```json
{
  "success": true,
  "steps": [
    {"name": "title", "status": "completed", "duration_ms": 1234},
    {"name": "correspondent", "status": "completed", "duration_ms": 567},
    ...
  ],
  "proposed_changes": {
    "title": "New Title",
    "correspondent": {"id": 5, "name": "Acme Corp"},
    "document_type": {"id": 3, "name": "Invoice"},
    "tags": [{"id": 1, "name": "Invoice"}, {"id": 2, "name": "Paid"}],
    "custom_fields": [{"id": 7, "name": "Amount", "value": "99.99"}]
  }
}
```

## Files to Modify

| File | Change |
|------|--------|
| `backend/app/routers/documents.py` | Add `/search` and `/preview/{doc_id}` endpoints |
| `backend/app/services/paperless.py` | Add `search` param to `list_documents` |
| `backend/app/services/processor.py` | Add `process_document_preview` method with `_resolve_proposed_changes` |
| `frontend/src/api/client.ts` | Add `searchPaperless` and `getPreview` |
| `frontend/src/pages/ChatPage.tsx` | Add search field, results, preview panel |
| `frontend/src/locales/en.json` | Add search/preview i18n keys |
| `frontend/src/locales/de.json` | Add search/preview i18n keys |

## Out of Scope

- Applying changes from preview (User goes to Processing page)
- OCR in preview
- Mobile responsive layout
- Changes to Processing page
