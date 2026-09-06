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
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow dark:shadow-none p-6 space-y-6">
      <div className="flex items-center justify-between border-b border-gray-200 dark:border-gray-700 pb-3 mb-4">
        <div className="flex items-center gap-2">
          <Brain size={18} className="text-blue-600 dark:text-blue-400" />
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100">{t('config.llmSection')}</h2>
        </div>
        <button
          onClick={handleTestLlm}
          disabled={testing}
          className="flex items-center gap-2 px-3 py-1.5 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50"
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
            <span className="font-normal text-gray-400 dark:text-gray-500">({t('common.optional')})</span>
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
          <div className="inline-flex rounded-lg border border-gray-300 dark:border-gray-600 overflow-hidden">
            <button
              type="button"
              onClick={() => handleChange('enable_vision', 'false')}
              className={`px-3 py-2 text-sm ${
                (config.enable_vision || 'false') === 'false'
                  ? 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100'
                  : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            >
              {t('common.disabled')}
            </button>
            <button
              type="button"
              onClick={() => handleChange('enable_vision', 'true')}
              className={`px-3 py-2 text-sm border-l border-gray-300 dark:border-gray-600 ${
                (config.enable_vision || 'false') === 'true'
                  ? 'bg-blue-50 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300'
                  : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
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
            className="w-32 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-gray-100"
          />
          <p className={hintClass}>{t('config.llmTimeoutHint')}</p>
        </div>
        <div>
          <label className={labelClass}>{t('config.llmTemperature')}</label>
          <input
            type="number"
            min="0"
            max="2"
            step="0.1"
            value={config.llm_temperature || '0.3'}
            onChange={(e) => handleChange('llm_temperature', e.target.value)}
            className="w-32 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-gray-100"
          />
          <p className={hintClass}>{t('config.llmTemperatureHint')}</p>
        </div>
        <div>
          <label className={labelClass}>{t('config.llmMaxTokens')}</label>
          <input
            type="number"
            min="1"
            step="1"
            value={config.llm_max_tokens || ''}
            onChange={(e) => handleChange('llm_max_tokens', e.target.value)}
            placeholder="4096"
            className="w-40 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-500"
          />
          <p className={hintClass}>{t('config.llmMaxTokensHint')}</p>
        </div>
        <div>
          <label htmlFor="llm-num-ctx" className={labelClass}>
            {t('config.llmContextWindow')}
          </label>
          <input
            id="llm-num-ctx"
            type="number"
            min="1"
            step="1"
            value={config.llm_num_ctx || ''}
            onChange={(e) => handleChange('llm_num_ctx', e.target.value)}
            placeholder="16384"
            className="w-40 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-500"
          />
          <p className={hintClass}>{t('config.llmContextWindowHint')}</p>
        </div>
      </div>
    </div>
  )
}
