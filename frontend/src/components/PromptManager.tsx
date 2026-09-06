import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { promptsApi, configApi } from '../api/client'
import { Plus, Pencil, Trash2, X, RefreshCw } from 'lucide-react'
import { MODULAR_TAG_DEFAULTS } from '../constants'

type SampleStatus =
  | 'custom'
  | 'sample_current'
  | 'sample_update_available'
  | 'modified'
  | 'legacy_sample'

const PROMPT_TYPE_TO_CONFIG_KEY: Record<string, string | undefined> = {
  title: 'modular_tag_title',
  correspondent: 'modular_tag_correspondent',
  document_type: 'modular_tag_document_type',
  tag: 'modular_tag_tags',
  extract: 'modular_tag_fields',
  type_specific: 'modular_tag_fields',
  vision_ocr: 'modular_tag_ocr',
  ocr_fix: 'modular_tag_ocr_fix',
  date: 'modular_tag_date',
  classify: 'modular_tag_process',
}

export function getTriggerTag(promptType: string, config: Record<string, string>): string | null {
  const configKey = PROMPT_TYPE_TO_CONFIG_KEY[promptType]
  if (!configKey) return null
  return config[configKey] ?? MODULAR_TAG_DEFAULTS[configKey] ?? null
}

interface Prompt {
  id: number
  name: string
  prompt_type: string
  document_type_filter: string | null
  system_prompt: string
  user_template: string
  is_active: boolean
  sample_key?: string | null
  sample_status?: SampleStatus
}

interface TemplateInfo {
  variables: { name: string; description: string }[]
  types: { value: string; description: string }[]
}

export default function PromptManager() {
  const { t } = useTranslation()
  const [prompts, setPrompts] = useState<Prompt[]>([])
  const [templates, setTemplates] = useState<TemplateInfo | null>(null)
  const [config, setConfig] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editingPrompt, setEditingPrompt] = useState<Prompt | null>(null)
  const [samplesMessage, setSamplesMessage] = useState<string | null>(null)
  const [formData, setFormData] = useState({
    name: '',
    prompt_type: 'classify',
    document_type_filter: '',
    system_prompt: '',
    user_template: '',
    is_active: true,
  })
  const userTemplateRequired = formData.prompt_type !== 'vision_ocr'
  const editingPromptWithStatus = editingPrompt
    ? prompts.find((prompt) => prompt.id === editingPrompt.id) || editingPrompt
    : null

  const loadData = useCallback(async () => {
    try {
      const [promptsRes, templatesRes, configRes] = await Promise.all([
        promptsApi.getAll(),
        promptsApi.getTemplates(),
        configApi.getAll(),
      ])
      setPrompts(promptsRes.data)
      setTemplates(templatesRes.data)
      setConfig(configRes.data as Record<string, string>)
    } catch (error) {
      console.error('Failed to load prompts:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      if (editingPrompt) {
        await promptsApi.update(editingPrompt.id, formData)
      } else {
        await promptsApi.create(formData)
      }
      setShowModal(false)
      setEditingPrompt(null)
      resetForm()
      loadData()
    } catch (error) {
      console.error('Failed to save prompt:', error)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm(t('prompts.confirmDelete'))) return
    try {
      await promptsApi.delete(id)
      loadData()
    } catch (error) {
      console.error('Failed to delete prompt:', error)
    }
  }

  const handleEdit = (prompt: Prompt) => {
    setEditingPrompt(prompt)
    setFormData({
      name: prompt.name,
      prompt_type: prompt.prompt_type,
      document_type_filter: prompt.document_type_filter || '',
      system_prompt: prompt.system_prompt,
      user_template: prompt.user_template,
      is_active: prompt.is_active,
    })
    setShowModal(true)
  }

  const resetForm = () => {
    setFormData({
      name: '',
      prompt_type: 'classify',
      document_type_filter: '',
      system_prompt: '',
      user_template: '',
      is_active: true,
    })
  }

  const handleLoadSamples = async () => {
    if (!confirm(t('prompts.confirmLoadSamples'))) return
    try {
      const res = await promptsApi.loadSamples()
      setSamplesMessage(
        t('prompts.samplesLoaded', { created: res.data.created, updated: res.data.updated }),
      )
      setTimeout(() => setSamplesMessage(null), 4000)
      loadData()
    } catch (error) {
      console.error('Failed to load samples:', error)
    }
  }

  const handleLoadPromptSample = async () => {
    if (!editingPrompt) return
    if (!confirm(t('prompts.confirmLoadPromptSample'))) return
    try {
      const res = await promptsApi.getSample(editingPrompt.id)
      const updated = res.data
      setFormData({
        name: updated.name,
        prompt_type: updated.prompt_type,
        document_type_filter: updated.document_type_filter || '',
        system_prompt: updated.system_prompt,
        user_template: updated.user_template,
        is_active: updated.is_active,
      })
    } catch (error) {
      console.error('Failed to load prompt sample:', error)
    }
  }

  const getSampleStatusClass = (status?: SampleStatus) => {
    switch (status) {
      case 'sample_current':
        return 'bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-300'
      case 'sample_update_available':
        return 'bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-300'
      case 'modified':
        return 'bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-300'
      case 'legacy_sample':
        return 'bg-yellow-100 dark:bg-yellow-900/40 text-yellow-800 dark:text-yellow-300'
      default:
        return 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200'
    }
  }

  const insertVariable = (variable: string, field: 'system' | 'user') => {
    const key = field === 'system' ? 'system_prompt' : 'user_template'
    setFormData({
      ...formData,
      [key]: formData[key] + variable,
    })
  }

  if (loading) {
    return <div className="text-gray-500 dark:text-gray-400">{t('common.loading')}</div>
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{t('prompts.title')}</h1>
        <div className="flex items-center gap-2">
          {samplesMessage && (
            <span className="text-sm text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-900/40 px-3 py-1 rounded-lg">
              {samplesMessage}
            </span>
          )}
          <button
            onClick={handleLoadSamples}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            <RefreshCw size={18} />
            {t('prompts.loadSamples')}
          </button>
          <button
            onClick={() => {
              resetForm()
              setEditingPrompt(null)
              setShowModal(true)
            }}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            <Plus size={20} />
            {t('prompts.addPrompt')}
          </button>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow dark:shadow-none overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-50 dark:bg-gray-900">
            <tr>
              <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                {t('prompts.colName')}
              </th>
              <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                {t('prompts.colType')}
              </th>
              <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                {t('prompts.colTypeFilter')}
              </th>
              <th
                className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400"
                title="Paperless tag that triggers this prompt"
              >
                Trigger Tag
              </th>
              <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                {t('prompts.colSample')}
              </th>
              <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                {t('prompts.colStatus')}
              </th>
              <th className="text-right py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                {t('prompts.colActions')}
              </th>
            </tr>
          </thead>
          <tbody>
            {prompts.map((prompt) => (
              <tr key={prompt.id} className="border-t border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700">
                <td className="py-3 px-4 font-medium text-gray-900 dark:text-gray-100">{prompt.name}</td>
                <td className="py-3 px-4">
                  <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 dark:text-gray-200 rounded text-xs">
                    {prompt.prompt_type}
                  </span>
                </td>
                <td className="py-3 px-4 text-gray-600 dark:text-gray-300">{prompt.document_type_filter || '-'}</td>
                <td className="py-3 px-4">
                  {(() => {
                    const tag = getTriggerTag(prompt.prompt_type, config)
                    return tag ? (
                      <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 font-mono text-xs rounded">
                        {tag}
                      </span>
                    ) : (
                      <span className="text-gray-400 dark:text-gray-500">—</span>
                    )
                  })()}
                </td>
                <td
                  className="py-3 px-4"
                  title={t(`prompts.sampleStatusHelp.${prompt.sample_status || 'custom'}`)}
                >
                  <span
                    className={`cursor-help px-2 py-1 rounded text-xs ${getSampleStatusClass(prompt.sample_status)}`}
                    title={t(`prompts.sampleStatusHelp.${prompt.sample_status || 'custom'}`)}
                  >
                    {t(`prompts.sampleStatus.${prompt.sample_status || 'custom'}`)}
                  </span>
                </td>
                <td className="py-3 px-4">
                  <span
                    className={`px-2 py-1 rounded text-xs ${prompt.is_active ? 'bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-300' : 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-100'}`}
                  >
                    {prompt.is_active ? t('prompts.active') : t('prompts.inactive')}
                  </span>
                </td>
                <td className="py-3 px-4 text-right">
                  <button
                    onClick={() => handleEdit(prompt)}
                    className="p-1 text-gray-600 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400"
                  >
                    <Pencil size={18} />
                  </button>
                  <button
                    onClick={() => handleDelete(prompt.id)}
                    className="p-1 text-gray-600 dark:text-gray-300 hover:text-red-600 dark:hover:text-red-400 ml-2"
                  >
                    <Trash2 size={18} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg w-full max-w-2xl max-h-[90vh] overflow-y-auto m-4">
            <div className="flex justify-between items-center p-4 border-b border-gray-200 dark:border-gray-700">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                {editingPrompt ? t('prompts.editPrompt') : t('prompts.createPrompt')}
              </h2>
              <button
                onClick={() => setShowModal(false)}
                className="text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
              >
                <X size={24} />
              </button>
            </div>
            <form onSubmit={handleSubmit} className="p-4 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                    {t('prompts.labelName')}
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    required
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:border-gray-600 dark:text-gray-100"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                    {t('prompts.labelType')}
                  </label>
                  <select
                    value={formData.prompt_type}
                    onChange={(e) => setFormData({ ...formData, prompt_type: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:border-gray-600 dark:text-gray-100"
                  >
                    {templates?.types.map((type) => (
                      <option key={type.value} value={type.value}>
                        {type.description}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {formData.prompt_type === 'type_specific' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                    {t('prompts.labelDocTypeFilter')}
                  </label>
                  <input
                    type="text"
                    value={formData.document_type_filter}
                    onChange={(e) =>
                      setFormData({ ...formData, document_type_filter: e.target.value })
                    }
                    placeholder={t('prompts.docTypeFilterPlaceholder')}
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:border-gray-600 dark:text-gray-100 dark:placeholder-gray-500"
                  />
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                  {t('prompts.labelSystemPrompt')}
                </label>
                {templates && (
                  <div className="flex gap-2 mb-2 flex-wrap">
                    {templates.variables.map((v) => (
                      <button
                        key={v.name}
                        type="button"
                        onClick={() => insertVariable(v.name, 'system')}
                        className="text-xs px-2 py-1 bg-blue-50 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400 rounded hover:bg-blue-100 dark:hover:bg-blue-900/60"
                      >
                        {v.name}
                      </button>
                    ))}
                  </div>
                )}
                <textarea
                  value={formData.system_prompt}
                  onChange={(e) => setFormData({ ...formData, system_prompt: e.target.value })}
                  required
                  rows={4}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:border-gray-600 dark:text-gray-100"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                  {t('prompts.labelUserTemplate')}
                </label>
                {templates && (
                  <div className="flex gap-2 mb-2 flex-wrap">
                    {templates.variables.map((v) => (
                      <button
                        key={v.name}
                        type="button"
                        onClick={() => insertVariable(v.name, 'user')}
                        className="text-xs px-2 py-1 bg-green-50 dark:bg-green-900/40 text-green-600 dark:text-green-400 rounded hover:bg-green-100 dark:hover:bg-green-900/60"
                      >
                        {v.name}
                      </button>
                    ))}
                  </div>
                )}
                <textarea
                  value={formData.user_template}
                  onChange={(e) => setFormData({ ...formData, user_template: e.target.value })}
                  required={userTemplateRequired}
                  rows={4}
                  placeholder={t('prompts.userTemplatePlaceholder')}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:border-gray-600 dark:text-gray-100 dark:placeholder-gray-500"
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="is_active"
                  checked={formData.is_active}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  className="rounded"
                />
                <label htmlFor="is_active" className="text-sm text-gray-700 dark:text-gray-200">
                  {t('prompts.labelActive')}
                </label>
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-gray-200 dark:border-gray-700">
                {editingPromptWithStatus?.sample_status
                  && editingPromptWithStatus.sample_status !== 'custom' && (
                  <button
                    type="button"
                    onClick={handleLoadPromptSample}
                    className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
                  >
                    {t('prompts.loadPromptSample')}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-gray-700 dark:text-gray-200 border dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
                >
                  {t('common.cancel')}
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  {editingPrompt ? t('prompts.update') : t('prompts.create')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
