import { useEffect, useState, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
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

const SENSITIVE_KEYS = new Set(['paperless_token', 'llm_api_key', 'llm_api_key_vision'])

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
  const navigate = useNavigate()
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
    enable_fallback_ocr: 'false',
    llm_provider_vision: 'ollama',
    llm_model_vision: 'qwen2.5vl:7b',
    llm_api_base_vision: 'http://localhost:11434',
    llm_timeout: '600',
    llm_timeout_vision: '600',
    log_level: 'INFO',
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
  })
  const [secretsSet, setSecretsSet] = useState<string[]>([])
  const [saving, setSaving] = useState(false)

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
    if (configs.auth_enabled === 'true' && !configs.paperless_url.trim()) {
      toast.warning(t('config.authRequiresPaperless'))
      setSaving(false)
      return
    }
    const entries = Object.entries(configs).filter(([, value]) => value !== '')
    const results = await Promise.allSettled(
      entries.map(([key, value]) => configApi.set(key, value)),
    )
    await configApi.set('auth_enabled', configs.auth_enabled)
    if (configs.auth_enabled === 'true') {
      navigate('/login')
      setSaving(false)
      return
    }
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
          <>
            <ConfigSectionLLM config={configs} onSave={handleSave} secretsSet={secretsSet} />
            {configs.enable_vision === 'true' && (
              <ConfigSectionVision config={configs} onSave={handleSave} secretsSet={secretsSet} />
            )}
          </>
        )
      case 'scheduler':
        return <ConfigSectionScheduler config={configs} onSave={handleSave} />
      case 'tags':
        return <ConfigSectionTags config={configs} onSave={handleSave} />
      case 'advanced':
        return <ConfigSectionAdvanced config={configs} onSave={handleSave} />
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