import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
          colSample: 'Sample',
          colStatus: 'Status',
          colActions: 'Actions',
          active: 'Active',
          inactive: 'Inactive',
          confirmDelete: 'Are you sure?',
          confirmLoadSamples: 'Load sample prompts?',
          confirmLoadPromptSample: 'Replace this prompt with the bundled sample?',
          samplesLoaded: 'Samples loaded',
          loadPromptSample: 'Load sample prompt',
          sampleStatus: {
            custom: 'Custom',
            sample_current: 'Sample current',
            sample_update_available: 'Sample update',
            modified: 'Modified',
            legacy_sample: 'Untracked',
          },
          sampleStatusHelp: {
            custom: 'no bundled sample',
            sample_current: 'matches current sample',
            sample_update_available: 'new sample available',
            modified: 'locally edited',
            legacy_sample: 'created before sample tracking or changed before tracking was available',
          },
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
          decisionHelp: 'Decision help',
          nimbleTitle: 'Nimble format',
          nimbleHelp: 'Nimble help',
          warnMissingPlaceholders: 'Saved, but the template is missing {{missing}}',
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

const { mockGet, mockPost, mockPut, mockToastWarning } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPut: vi.fn(),
  mockToastWarning: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: mockToastWarning },
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
    update: mockPut,
    delete: mockPost,
    loadSample: mockPost,
    getSample: mockGet,
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

const decisionType = {
  value: 'decision_correspondent',
  description: 'Decision: correspondent (letters)',
  variables: [
    { name: '{content}', description: 'c' },
    { name: '{question}', description: 'q' },
    { name: '{options}', description: 'o' },
  ],
}
const templatesWithDecision = { ...mockTemplates, types: [...mockTemplates.types, decisionType] }

function loadWith(templates = templatesWithDecision) {
  mockGet
    .mockResolvedValueOnce(createMockResponse(mockPrompts))
    .mockResolvedValueOnce(createMockResponse(templates))
    .mockResolvedValueOnce(createMockResponse(mockConfig))
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

  it('returns OCR trigger tag defaults for vision OCR and OCR Fix prompts', () => {
    expect(getTriggerTag('vision_ocr', {})).toBe('ai-ocr')
    expect(getTriggerTag('ocr_fix', {})).toBe('ai-ocr-fix')
  })

  it('returns date trigger tag default when config key is not present', () => {
    expect(getTriggerTag('date', {})).toBe('ai-date')
  })

  it('returns configured date trigger tag when modular tag is present', () => {
    expect(getTriggerTag('date', { modular_tag_date: 'detect-document-date' })).toBe(
      'detect-document-date',
    )
  })

  it('shows the trigger tag for the decision types', () => {
    expect(getTriggerTag('decision_correspondent', {})).toBe('ai-correspondent')
    expect(getTriggerTag('decision_document_type', { modular_tag_document_type: 'typ' })).toBe('typ')
  })
})

describe('PromptManager Component', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
    mockPut.mockReset()
    mockToastWarning.mockReset()
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

  it('shows different trigger tags for active Vision OCR and OCR Fix prompts', async () => {
    mockGet
      .mockResolvedValueOnce(
        createMockResponse([
          {
            id: 10,
            name: 'Vision OCR',
            prompt_type: 'vision_ocr',
            document_type_filter: null,
            system_prompt: 'Read the document',
            user_template: '',
            is_active: true,
          },
          {
            id: 11,
            name: 'OCR Fix',
            prompt_type: 'ocr_fix',
            document_type_filter: null,
            system_prompt: 'Fix OCR errors',
            user_template: 'Content: {{content}}',
            is_active: true,
          },
        ]),
      )
      .mockResolvedValueOnce(createMockResponse(mockTemplates))
      .mockResolvedValueOnce(createMockResponse({}))

    render(<PromptManager />)

    await waitFor(() => {
      expect(screen.getByText('Vision OCR')).toBeInTheDocument()
      expect(screen.getByText('OCR Fix')).toBeInTheDocument()
      expect(screen.getByText('ai-ocr')).toBeInTheDocument()
      expect(screen.getByText('ai-ocr-fix')).toBeInTheDocument()
    })
  })

  it('shows date trigger tag for active date prompts', async () => {
    mockGet
      .mockResolvedValueOnce(
        createMockResponse([
          {
            id: 12,
            name: 'Detect Date',
            prompt_type: 'date',
            document_type_filter: null,
            system_prompt: 'Detect document date',
            user_template: 'Content: {{content}}',
            is_active: true,
          },
        ]),
      )
      .mockResolvedValueOnce(createMockResponse(mockTemplates))
      .mockResolvedValueOnce(createMockResponse({ modular_tag_date: 'detect-document-date' }))

    render(<PromptManager />)

    await waitFor(() => {
      expect(screen.getByText('Detect Date')).toBeInTheDocument()
      expect(screen.getByText('detect-document-date')).toBeInTheDocument()
    })
  })

  it('shows sample status badges for prompts', async () => {
    mockGet
      .mockResolvedValueOnce(
        createMockResponse([
          {
            id: 12,
            name: 'Date Detection',
            prompt_type: 'date',
            document_type_filter: null,
            system_prompt: 'Detect date',
            user_template: 'Content',
            is_active: true,
            sample_key: 'date-detection',
            sample_status: 'legacy_sample',
          },
        ]),
      )
      .mockResolvedValueOnce(createMockResponse(mockTemplates))
      .mockResolvedValueOnce(createMockResponse({}))

    render(<PromptManager />)

    expect(await screen.findByText('Date Detection')).toBeInTheDocument()
    const status = screen.getByText('Untracked')
    expect(status).toBeInTheDocument()
    expect(status).toHaveAttribute(
      'title',
      'created before sample tracking or changed before tracking was available',
    )
  })

  it('loads the bundled sample into the edit form without saving', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockGet
      .mockResolvedValueOnce(
        createMockResponse([
          {
            id: 12,
            name: 'Date Detection',
            prompt_type: 'date',
            document_type_filter: null,
            system_prompt: 'Old date prompt',
            user_template: 'Old template',
            is_active: true,
            sample_key: 'date-detection',
            sample_status: 'legacy_sample',
          },
        ]),
      )
      .mockResolvedValueOnce(createMockResponse(mockTemplates))
      .mockResolvedValueOnce(createMockResponse({}))
      .mockResolvedValueOnce(
        createMockResponse({
          name: 'Date Detection',
          prompt_type: 'date',
          document_type_filter: null,
          system_prompt: 'New bundled date prompt',
          user_template: 'Current date: {current_date}',
          is_active: true,
          sample_key: 'date-detection',
        }),
      )

    const { container } = render(<PromptManager />)

    await screen.findByText('Date Detection')
    const editButton = container.querySelector('tbody button')
    await user.click(editButton as HTMLButtonElement)
    await user.click(screen.getByRole('button', { name: /load sample prompt/i }))

    expect(mockGet).toHaveBeenLastCalledWith(12)
    expect(mockPost).not.toHaveBeenCalledWith(12)
    expect(mockPut).not.toHaveBeenCalled()
    expect(screen.getByDisplayValue('New bundled date prompt')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Current date: {current_date}')).toBeInTheDocument()
  })

  it('allows saving a Vision OCR prompt with an empty user template', async () => {
    const user = userEvent.setup()
    mockPut.mockResolvedValue(createMockResponse({}))
    mockGet
      .mockResolvedValueOnce(
        createMockResponse([
          {
            id: 10,
            name: 'Vision OCR',
            prompt_type: 'vision_ocr',
            document_type_filter: null,
            system_prompt: 'Read the document',
            user_template: 'Existing template',
            is_active: true,
          },
        ]),
      )
      .mockResolvedValueOnce(createMockResponse(mockTemplates))
      .mockResolvedValueOnce(createMockResponse({}))
      .mockResolvedValueOnce(createMockResponse([]))
      .mockResolvedValueOnce(createMockResponse(mockTemplates))
      .mockResolvedValueOnce(createMockResponse({}))

    const { container } = render(<PromptManager />)

    await screen.findByText('Vision OCR')
    const editButton = container.querySelector('tbody button')
    expect(editButton).not.toBeNull()
    await user.click(editButton as HTMLButtonElement)

    const textareas = screen.getAllByRole('textbox')
    const userTemplate = textareas[textareas.length - 1]
    await user.clear(userTemplate)
    await user.click(screen.getByRole('button', { name: /update/i }))

    await waitFor(() => {
      expect(mockPut).toHaveBeenCalledWith(10, {
        name: 'Vision OCR',
        prompt_type: 'vision_ocr',
        document_type_filter: '',
        system_prompt: 'Read the document',
        user_template: '',
        is_active: true,
      })
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

  it('offers only the decision placeholders for a decision prompt', async () => {
    loadWith()
    render(<PromptManager />)
    await userEvent.click(await screen.findByText('Add Prompt'))
    await userEvent.selectOptions(screen.getByLabelText('Type'), 'decision_correspondent')
    expect(screen.getAllByText('{options}').length).toBeGreaterThan(0)
    expect(screen.getAllByText('{content}').length).toBeGreaterThan(0)
    expect(screen.queryByText('{{text}}')).not.toBeInTheDocument()
    expect(screen.getByText('Decision help')).toBeInTheDocument()
  })

  it('toasts the missing placeholders after a save', async () => {
    loadWith()
    mockPost.mockResolvedValueOnce(
      createMockResponse({
        id: 9,
        name: 'x',
        message: 'ok',
        warning: { code: 'missing_placeholders', missing: ['{options}'] },
      }),
    )
    loadWith() // the list reloads after the save
    render(<PromptManager />)
    await userEvent.click(await screen.findByText('Add Prompt'))
    await userEvent.type(screen.getByLabelText('Name'), 'x')
    await userEvent.selectOptions(screen.getByLabelText('Type'), 'decision_correspondent')
    await userEvent.type(screen.getByLabelText('System Prompt'), 'Pick one.')
    await userEvent.type(screen.getByLabelText('User Template'), '{{content} {{question}')
    await userEvent.click(screen.getByText('Create'))
    await waitFor(() => {
      expect(mockToastWarning).toHaveBeenCalledWith('Saved, but the template is missing {options}')
    })
  })

  it('shows the Nimble format read-only', async () => {
    loadWith()
    render(<PromptManager />)
    expect(await screen.findByText('Nimble format')).toBeInTheDocument()
    expect(screen.getByText(/Requested field/)).toBeInTheDocument()
    expect(screen.getByText('Nimble help')).toBeInTheDocument()
  })
})
