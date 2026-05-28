import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Brain, RefreshCw, CheckCircle } from 'lucide-react'
import { toast } from 'sonner'
import { configApi } from '../api/client'
import { ConfigSectionProps } from './ConfigSectionProps'
import { fieldClass, labelClass, hintClass } from './fieldStyles'

export function ConfigSectionLLM({ config, onSave, secretsSet }: ConfigSectionProps) {
  const { t } = useTranslation()
  const [testing, setTesting] = useState(false)

  const handleChange = async (key: string, value: string) => {
    await onSave(key, value)
  }

  const handleTestLlm = async () => {
    setTesting(true)
    try {
      const res = await configApi.testConnection()
      const data = res.data

      let message = ''
      if (data.main) message += `Main: ${data.main.message}`
      if (data.vision !== null && data.vision !== undefined)
        message += `\nVision: ${data.vision.message}`

      if (data.success) {
        toast.success(message)
      } else {
        toast.error(message)
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Connection failed'
      toast.error(`Error: ${message}`)
    } finally {
      setTesting(false)
    }
  }

  const getModelPlaceholder = (provider: string) => {
    if (provider === 'openai') return 'gpt-4o-mini'
    if (provider === 'grok') return 'grok-3-mini'
    if (provider === 'openrouter') return 'openai/gpt-4o-mini'
    return 'qwen2.5:7b'
  }

  const getApiBasePlaceholder = (provider: string) => {
    if (provider === 'openai') return 'https://api.openai.com/v1'
    if (provider === 'grok') return 'https://api.x.ai/v1'
    if (provider === 'openrouter') return 'https://openrouter.ai/api/v1'
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
            <option value="openrouter">OpenRouter</option>
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
          <div className="inline-flex rounded-lg border border-gray-300 overflow-hidden">
            <button
              type="button"
              onClick={() => handleChange('enable_vision', 'false')}
              className={`px-3 py-2 text-sm ${
                (config.enable_vision || 'false') === 'false'
                  ? 'bg-gray-100 text-gray-900'
                  : 'bg-white text-gray-600 hover:bg-gray-50'
              }`}
            >
              {t('common.disabled')}
            </button>
            <button
              type="button"
              onClick={() => handleChange('enable_vision', 'true')}
              className={`px-3 py-2 text-sm border-l border-gray-300 ${
                (config.enable_vision || 'false') === 'true'
                  ? 'bg-blue-50 text-blue-700'
                  : 'bg-white text-gray-600 hover:bg-gray-50'
              }`}
            >
              {t('common.enabled')}
            </button>
          </div>
          <p className={hintClass}>{t('config.visionOcrHint')}</p>
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
    </div>
  )
}
