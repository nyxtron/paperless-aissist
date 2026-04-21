import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { getTriggerTag } from '../components/PromptManager'
import PromptManager from '../components/PromptManager'

i18n.use(initReactI18next).init({
  resources: {
    en: {
      translation: {
        prompts: {
          title: 'Prompts',
          addPrompt: 'Add Prompt',
          loadSamples: 'Load Samples',
          colName: 'Name',
          colType: 'Type',
          colTypeFilter: 'Type Filter',
          colStatus: 'Status',
          colActions: 'Actions',
          active: 'Active',
          inactive: 'Inactive',
          confirmDelete: 'Are you sure?',
          confirmLoadSamples: 'Load sample prompts?',
          samplesLoaded: 'Samples loaded',
          editPrompt: 'Edit Prompt',
          createPrompt: 'Create Prompt',
          labelName: 'Name',
          labelType: 'Type',
          labelDocTypeFilter: 'Document Type Filter',
          docTypeFilterPlaceholder: 'e.g. Invoice, Receipt',
          labelSystemPrompt: 'System Prompt',
          labelUserTemplate: 'User Template',
          userTemplatePlaceholder: 'Optional user template...',
          labelActive: 'Active',
          update: 'Update',
          create: 'Create',
          cancel: 'Cancel',
        },
        common: {
          loading: 'Loading...',
        },
      },
    },
  },
  lng: 'en',
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}))

vi.mock('../api/client', () => ({
  default: {
    get: mockGet,
    post: mockPost,
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
  configApi: {
    getAll: mockGet,
  },
  documentsApi: {},
  statsApi: {},
  schedulerApi: {},
  promptsApi: {
    getAll: mockGet,
    getTemplates: mockGet,
    loadSamples: mockPost,
    create: mockPost,
    update: mockPost,
    delete: mockPost,
  },
}))

function createMockResponse(data: any) {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {},
  }
}

const mockPrompts = [
  {
    id: 1,
    name: 'Classify Doc',
    prompt_type: 'classify',
    document_type_filter: null,
    system_prompt: 'Classify this document',
    user_template: 'Content: {{content}}',
    is_active: true,
  },
  {
    id: 2,
    name: 'Extract Fields',
    prompt_type: 'extract',
    document_type_filter: 'Invoice',
    system_prompt: 'Extract fields',
    user_template: 'Text: {{text}}',
    is_active: true,
  },
]

const mockTemplates = {
  variables: [
    { name: '{{content}}', description: 'Document content' },
    { name: '{{text}}', description: 'Extracted text' },
  ],
  types: [
    { value: 'classify', description: 'Classification' },
    { value: 'extract', description: 'Field Extraction' },
  ],
}

const mockConfig: Record<string, string> = {
  modular_tag_title: 'custom-title-tag',
  modular_tag_ocr: 'custom-ocr-tag',
}

describe('getTriggerTag', () => {
  it('returns config value for known prompt type', () => {
    const result = getTriggerTag('title', { modular_tag_title: 'custom-title-tag' })
    expect(result).toBe('custom-title-tag')
  })

  it('returns empty string when config key is empty string (no fallback)', () => {
    const result = getTriggerTag('title', { modular_tag_title: '' })
    expect(result).toBe('')
  })

  it('returns null for unknown prompt type', () => {
    const result = getTriggerTag('unknown_type', {})
    expect(result).toBeNull()
  })

  it('returns default when config key is not present', () => {
    const result = getTriggerTag('title', {})
    expect(result).toBe('ai-title')
  })
})

describe('PromptManager Component', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
  })

  it('renders prompt list after loading', async () => {
    mockGet
      .mockResolvedValueOnce(createMockResponse(mockPrompts))
      .mockResolvedValueOnce(createMockResponse(mockTemplates))
      .mockResolvedValueOnce(createMockResponse(mockConfig))

    render(<PromptManager />)

    await waitFor(() => {
      expect(screen.getByText('Classify Doc')).toBeInTheDocument()
      expect(screen.getByText('Extract Fields')).toBeInTheDocument()
    })
  })

  it('shows trigger tags for prompts', async () => {
    mockGet
      .mockResolvedValueOnce(createMockResponse(mockPrompts))
      .mockResolvedValueOnce(createMockResponse(mockTemplates))
      .mockResolvedValueOnce(createMockResponse(mockConfig))

    render(<PromptManager />)

    await waitFor(() => {
      const tagCells = screen.getAllByText('ai-process')
      expect(tagCells.length).toBe(1)
    })
  })

  it('renders add prompt button', async () => {
    mockGet
      .mockResolvedValueOnce(createMockResponse([]))
      .mockResolvedValueOnce(createMockResponse(mockTemplates))
      .mockResolvedValueOnce(createMockResponse({}))

    await i18n.init()
    render(<PromptManager />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /add prompt/i })).toBeInTheDocument()
    })
  })
})
