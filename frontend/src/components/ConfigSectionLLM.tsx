import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Brain, RefreshCw, CheckCircle, XCircle } from 'lucide-react'
import { configApi } from '../api/client'
import { ConfigSectionProps } from './ConfigSectionProps'
import { fieldClass, labelClass, hintClass } from './fieldStyles'

interface LlmResult {
  success: boolean
  message: string
}

export function ConfigSectionLLM({ config, onSave, secretsSet }: ConfigSectionProps) {
  const { t } = useTranslation()
  const [testing, setTesting] = useState(false)
  const [llmResult, setLlmResult] = useState<LlmResult | null>(null)

  const handleChange = async (key: string, value: string) => {
    await onSave(key, value)
  }

  const handleTestLlm = async () => {
    setTesting(true)
    setLlmResult(null)
    try {
      const res = await configApi.testConnection()
      const data = res.data

      let message = ''
      if (data.main) message += `Main: ${data.main.message}`
      if (data.vision !== null && data.vision !== undefined)
        message += `\nVision: ${data.vision.message}`

      setLlmResult({ success: data.success, message })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Connection failed'
      setLlmResult({ success: false, message: `Error: ${message}` })
    } finally {
      setTesting(false)
    }
  }

  const getModelPlaceholder = (provider: string) => {
    if (provider === 'openai') return 'gpt-4o-mini'
    if (provider === 'grok') return 'grok-3-mini'
    return 'qwen2.5:7b'
  }

  const getApiBasePlaceholder = (provider: string) => {
    if (provider === 'openai') return 'https://api.openai.com/v1'
    if (provider === 'grok') return 'https://api.x.ai/v1'
    return 'http://localhost:11434'
  }

  const getApiKeyPlaceholder = (provider: string) => {
    if (provider === 'ollama') return t('config.apiKeyPlaceholderOllama')
    return t('config.apiKeyPlaceholderCloud')
  }

  return (
    <div className="bg-white rounded-lg shadow p-6 space-y-6">
      <div className="flex items-center justify-between border-b pb-3 mb-4">
        <div className="flex items-center gap-2">
          <Brain size={18} className="text-blue-600" />
          <h2 className="text-lg font-semibold text-gray-800">{t('config.llmSection')}</h2>
        </div>
        <button
          onClick={handleTestLlm}
          disabled={testing}
          className="flex items-center gap-2 px-3 py-1.5 text-sm bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50"
        >
          {testing ? <RefreshCw size={14} className="animate-spin" /> : <CheckCircle size={14} />}
          {t('config.testConnection')}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>{t('config.provider')}</label>
          <select
            value={config.llm_provider || 'ollama'}
            onChange={(e) => handleChange('llm_provider', e.target.value)}
            className={fieldClass}
          >
            <option value="ollama">Ollama</option>
            <option value="openai">OpenAI</option>
            <option value="grok">Grok (xAI)</option>
          </select>
        </div>
        <div>
          <label className={labelClass}>{t('config.model')}</label>
          <input
            type="text"
            value={config.llm_model || ''}
            onChange={(e) => handleChange('llm_model', e.target.value)}
            placeholder={getModelPlaceholder(config.llm_provider)}
            className={fieldClass}
          />
        </div>
        <div>
          <label className={labelClass}>{t('config.apiBaseUrl')}</label>
          <input
            type="text"
            value={config.llm_api_base || ''}
            onChange={(e) => handleChange('llm_api_base', e.target.value)}
            placeholder={getApiBasePlaceholder(config.llm_provider)}
            className={fieldClass}
          />
        </div>
        <div>
          <label className={labelClass}>
            {t('config.apiKey')}{' '}
            <span className="font-normal text-gray-400">({t('common.optional')})</span>
          </label>
          <input
            type="password"
            value={config.llm_api_key || ''}
            onChange={(e) => handleChange('llm_api_key', e.target.value)}
            placeholder={
              secretsSet?.includes('llm_api_key')
                ? t('config.alreadySetPlaceholder')
                : getApiKeyPlaceholder(config.llm_provider)
            }
            className={fieldClass}
          />
          <p className={hintClass}>{t('config.apiKeyHint')}</p>
        </div>
        <div>
          <label className={labelClass}>{t('config.visionOcr')}</label>
          <select
            value={config.enable_vision || 'false'}
            onChange={(e) => handleChange('enable_vision', e.target.value)}
            className={fieldClass}
          >
            <option value="false">{t('common.disabled')}</option>
            <option value="true">{t('common.enabled')}</option>
          </select>
          <p className={hintClass}>{t('config.visionOcrHint')}</p>
        </div>
        <div>
          <label className={labelClass}>{t('config.fallbackOcr')}</label>
          <select
            value={config.enable_fallback_ocr || 'false'}
            onChange={(e) => handleChange('enable_fallback_ocr', e.target.value)}
            className={fieldClass}
          >
            <option value="false">{t('common.disabled')}</option>
            <option value="true">{t('common.enabled')}</option>
          </select>
          <p className={hintClass}>{t('config.fallbackOcrHint')}</p>
        </div>
        <div>
          <label className={labelClass}>{t('config.llmTimeout')}</label>
          <input
            type="number"
            min="30"
            max="3600"
            value={config.llm_timeout || '600'}
            onChange={(e) => handleChange('llm_timeout', e.target.value)}
            className="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
          />
          <p className={hintClass}>{t('config.llmTimeoutHint')}</p>
        </div>
      </div>

      {llmResult && (
        <div
          className={`flex items-start gap-2 px-3 py-2 rounded-lg text-sm ${
            llmResult.success ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          }`}
        >
          {llmResult.success ? (
            <CheckCircle size={16} className="mt-0.5 shrink-0" />
          ) : (
            <XCircle size={16} className="mt-0.5 shrink-0" />
          )}
          <span className="whitespace-pre-line">{llmResult.message}</span>
        </div>
      )}
    </div>
  )
}
