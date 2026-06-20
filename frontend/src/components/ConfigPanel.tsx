import { useEffect, useState, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { configApi } from '../api/client'
import { ConfigSectionPaperless } from './ConfigSectionPaperless'
import { ConfigSectionLLM } from './ConfigSectionLLM'
import { ConfigSectionVision } from './ConfigSectionVision'
import { ConfigSectionScheduler } from './ConfigSectionScheduler'
import { ConfigSectionTags } from './ConfigSectionTags'
import { ConfigSectionAdvanced } from './ConfigSectionAdvanced'
import { Server, Brain, Clock, Tag, Settings } from 'lucide-react'

const SENSITIVE_KEYS = new Set([
  'paperless_token',
  'llm_api_key',
  'llm_api_key_vision',
  'automation_api_token_hash',
])
const IMMEDIATE_SAVE_KEYS = new Set(['document_list_refresh_mode'])

const TAB_CONFIG = [
  { id: 'paperless', labelKey: 'config.tabServer', Icon: Server },
  { id: 'llm', labelKey: 'config.tabLLM', Icon: Brain },
  { id: 'scheduler', labelKey: 'config.tabScheduler', Icon: Clock },
  { id: 'tags', labelKey: 'config.tabTags', Icon: Tag },
  { id: 'advanced', labelKey: 'config.tabAdvanced', Icon: Settings },
] as const

type TabId = typeof TAB_CONFIG[number]['id']

export default function ConfigPanel() {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<TabId>('paperless')
  const [configs, setConfigs] = useState<Record<string, string>>({
    paperless_url: '',
    process_tag: '',
    processed_tag: '',
    tag_blacklist: '',
    force_ocr_tag: 'force_ocr',
    force_ocr_fix_tag: 'force-ocr-fix',
    ocr_post_process: 'true',
    llm_provider: 'ollama',
    llm_model: 'qwen2.5:7b',
    llm_api_base: 'http://localhost:11434',
    enable_vision: 'false',
    llm_provider_vision: 'ollama',
    llm_model_vision: 'qwen2.5vl:7b',
    llm_api_base_vision: 'http://localhost:11434',
    vision_pdf_mode: 'auto',
    llm_timeout: '600',
    llm_timeout_vision: '600',
    llm_temperature: '0.3',
    llm_temperature_vision: '0.3',
    llm_max_tokens: '',
    llm_max_tokens_vision: '',
    llm_num_ctx: '',
    llm_num_ctx_vision: '',
    log_level: 'INFO',
    ocr_fix_max_chars: '10000',
    document_list_refresh_mode: 'automatic',
    modular_tag_process: '',
    modular_tag_ocr: '',
    modular_tag_ocr_fix: '',
    modular_tag_title: '',
    modular_tag_correspondent: '',
    modular_tag_document_type: '',
    modular_tag_tags: '',
    modular_tag_fields: '',
    modular_processed_tag: '',
    auth_enabled: 'false',
    mcp_enabled: 'false',
  })
  const [secretsSet, setSecretsSet] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [initialAuthEnabled, setInitialAuthEnabled] = useState<'true' | 'false'>('false')

  const saveTimeoutsRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  useEffect(() => {
    return () => {
      for (const timeout of saveTimeoutsRef.current.values()) clearTimeout(timeout)
    }
  }, [])

  const loadConfigs = useCallback(async () => {
    try {
      const res = await configApi.getAll()
      const { data, secrets_set } = res.data as { data: Record<string, string>; secrets_set: string[] }
      setConfigs((prev) => ({ ...prev, ...data }))
      setSecretsSet(secrets_set || [])
      setInitialAuthEnabled((data.auth_enabled as 'true' | 'false') || 'false')
    } catch (error) {
      console.error('Failed to load configs:', error)
    }
  }, [])

  useEffect(() => {
    loadConfigs()
  }, [loadConfigs])

  const handleSave = useCallback((key: string, value: string): Promise<void> => {
    return new Promise((resolve) => {
      const existing = saveTimeoutsRef.current.get(key)
      if (existing) clearTimeout(existing)
      if (SENSITIVE_KEYS.has(key) && !value) {
        resolve()
        return
      }
      setConfigs((prev) => ({ ...prev, [key]: value }))
      if (IMMEDIATE_SAVE_KEYS.has(key)) {
        configApi.set(key, value)
          .catch((e) => {
            console.error(`Failed to save ${key}:`, e)
          })
          .finally(resolve)
        return
      }
      const timeoutId = setTimeout(async () => {
        saveTimeoutsRef.current.delete(key)
        try {
          await configApi.set(key, value)
        } catch (e) {
          console.error(`Failed to save ${key}:`, e)
        }
        resolve()
      }, 1000)
      saveTimeoutsRef.current.set(key, timeoutId)
    })
  }, [])

  const handleSaveAll = async () => {
    setSaving(true)
    const shouldForceLogin = initialAuthEnabled !== 'true' && configs.auth_enabled === 'true'

    if (configs.auth_enabled === 'true' && !configs.paperless_url.trim()) {
      toast.warning(t('config.authRequiresPaperless'))
      setSaving(false)
      return
    }

    // Flush all debounced saves first to avoid race conditions
    for (const [, timeoutId] of saveTimeoutsRef.current) {
      clearTimeout(timeoutId)
    }
    saveTimeoutsRef.current.clear()

    const entries = Object.entries(configs).filter(([key, value]) => value !== '' && key !== 'auth_enabled')
    const results = await Promise.allSettled(
      entries.map(([key, value]) => configApi.set(key, value)),
    )

    // Save auth_enabled last so other saves aren't blocked by new auth requirement
    if (configs.auth_enabled) {
      try {
        await configApi.set('auth_enabled', configs.auth_enabled)
      } catch (e) {
        console.error('Failed to save auth_enabled:', e)
        toast.error(t('config.saveFailed'))
        setSaving(false)
        return
      }
    }

    if (shouldForceLogin) {
      // Clear token and force full page reload to reset auth state
      localStorage.removeItem('paperless_token')
      setSaving(false)
      window.location.href = '/login'
      return
    }

    setInitialAuthEnabled((configs.auth_enabled as 'true' | 'false') || 'false')

    const failures = results.filter((r) => r.status === 'rejected')
    if (failures.length > 0) {
      toast.error(t('config.saveFailed'))
    } else {
      toast.success(t('config.savedSuccess'))
    }
    setSaving(false)
  }

  const renderActiveSection = () => {
    switch (activeTab) {
      case 'paperless':
        return <ConfigSectionPaperless config={configs} onSave={handleSave} secretsSet={secretsSet} />
      case 'llm':
        return (
          <div className="space-y-4">
            <ConfigSectionLLM config={configs} onSave={handleSave} secretsSet={secretsSet} />
            <ConfigSectionVision config={configs} onSave={handleSave} secretsSet={secretsSet} />
          </div>
        )
      case 'scheduler':
        return <ConfigSectionScheduler config={configs} onSave={handleSave} />
      case 'tags':
        return <ConfigSectionTags config={configs} onSave={handleSave} />
      case 'advanced':
        return (
          <ConfigSectionAdvanced
            config={configs}
            onSave={handleSave}
            secretsSet={secretsSet}
            onSecretsChanged={loadConfigs}
          />
        )
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">{t('config.title')}</h1>
      </div>

      <div className="border-b border-gray-200">
        <nav className="flex gap-1 -mb-px overflow-x-auto">
          {TAB_CONFIG.map(({ id, labelKey, Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id as TabId)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                activeTab === id
                  ? 'text-blue-600 border-blue-600'
                  : 'text-gray-500 border-transparent hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <Icon size={16} />
              {t(labelKey)}
            </button>
          ))}
        </nav>
      </div>

      {renderActiveSection()}

      <div className="flex justify-end">
        <button
          onClick={handleSaveAll}
          disabled={saving}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? t('config.saving') : t('config.saveConfiguration')}
        </button>
      </div>
    </div>
  )
}
