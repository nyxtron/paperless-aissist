import { useTranslation } from 'react-i18next'
import { ConfigSectionProps } from './ConfigSectionProps'
import { fieldClass, labelClass, hintClass } from './fieldStyles'

export function ConfigSectionVision({ config, onSave, secretsSet }: ConfigSectionProps) {
  const { t } = useTranslation()
  const visionEnabled = (config.enable_vision || 'false') === 'true'

  const handleChange = async (key: string, value: string) => {
    await onSave(key, value)
  }

  const getVisionModelPlaceholder = (provider: string) => {
    if (provider === 'openai') return 'gpt-4o'
    if (provider === 'grok') return 'grok-2-vision-1212'
    if (provider === 'openrouter') return 'openai/gpt-4o'
    return 'qwen2.5vl:7b'
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
    <div className="bg-blue-50/50 dark:bg-blue-950/40 border border-blue-100 dark:border-blue-900 rounded-lg shadow-sm dark:shadow-none p-6 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-blue-100 dark:border-blue-900 pb-3 mb-4">
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">{t('config.visionModelSection')}</h3>
        <span
          className={`text-xs px-2 py-1 rounded-full ${
            visionEnabled ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
          }`}
        >
          {visionEnabled ? t('common.enabled') : t('common.disabled')}
        </span>
      </div>
      {!visionEnabled && <p className={hintClass}>{t('config.visionSectionDisabledHint')}</p>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>{t('config.provider')}</label>
          <select
            value={config.llm_provider_vision || 'ollama'}
            onChange={(e) => handleChange('llm_provider_vision', e.target.value)}
            className={fieldClass}
          >
            <option value="ollama">Ollama</option>
            <option value="openai">OpenAI</option>
            <option value="grok">Grok (xAI)</option>
            <option value="openrouter">OpenRouter</option>
          </select>
        </div>
        <div>
          <label className={labelClass}>{t('config.visionModel')}</label>
          <input
            type="text"
            value={config.llm_model_vision || ''}
            onChange={(e) => handleChange('llm_model_vision', e.target.value)}
            placeholder={getVisionModelPlaceholder(config.llm_provider_vision)}
            className={fieldClass}
          />
        </div>
        <div>
          <label className={labelClass}>{t('config.apiBaseUrl')}</label>
          <input
            type="text"
            value={config.llm_api_base_vision || ''}
            onChange={(e) => handleChange('llm_api_base_vision', e.target.value)}
            placeholder={getApiBasePlaceholder(config.llm_provider_vision)}
            className={fieldClass}
          />
        </div>
        <div>
          <label htmlFor="vision-pdf-mode" className={labelClass}>
            {t('config.visionPdfMode')}
          </label>
          <select
            id="vision-pdf-mode"
            value={config.vision_pdf_mode || 'auto'}
            onChange={(e) => handleChange('vision_pdf_mode', e.target.value)}
            className={fieldClass}
          >
            <option value="auto">{t('config.visionPdfModeAuto')}</option>
            <option value="native_pdf">{t('config.visionPdfModeNative')}</option>
            <option value="page_images">{t('config.visionPdfModeImages')}</option>
          </select>
          <p className={hintClass}>{t('config.visionPdfModeHelp')}</p>
        </div>
        <div>
          <label className={labelClass}>
            {t('config.apiKey')}{' '}
            <span className="font-normal text-gray-400 dark:text-gray-500">({t('common.optional')})</span>
          </label>
          <input
            type="password"
            value={config.llm_api_key_vision || ''}
            onChange={(e) => handleChange('llm_api_key_vision', e.target.value)}
            placeholder={
              secretsSet?.includes('llm_api_key_vision')
                ? t('config.alreadySetPlaceholder')
                : getApiKeyPlaceholder(config.llm_provider_vision)
            }
            className={fieldClass}
          />
          <p className={hintClass}>{t('config.apiKeyHint')}</p>
        </div>
        <div>
          <label className={labelClass}>{t('config.llmTimeoutVision')}</label>
          <input
            type="number"
            min="30"
            max="3600"
            value={config.llm_timeout_vision || '600'}
            onChange={(e) => handleChange('llm_timeout_vision', e.target.value)}
            className="w-32 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-gray-100"
          />
          <p className={hintClass}>{t('config.llmTimeoutVisionHint')}</p>
        </div>
        <div>
          <label className={labelClass}>{t('config.llmTemperatureVision')}</label>
          <input
            type="number"
            min="0"
            max="2"
            step="0.1"
            value={config.llm_temperature_vision || '0.3'}
            onChange={(e) => handleChange('llm_temperature_vision', e.target.value)}
            className="w-32 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-gray-100"
          />
          <p className={hintClass}>{t('config.llmTemperatureVisionHint')}</p>
        </div>
        <div>
          <label className={labelClass}>{t('config.llmMaxTokensVision')}</label>
          <input
            type="number"
            min="1"
            step="1"
            value={config.llm_max_tokens_vision || ''}
            onChange={(e) => handleChange('llm_max_tokens_vision', e.target.value)}
            placeholder="8192"
            className="w-40 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-500"
          />
          <p className={hintClass}>{t('config.llmMaxTokensVisionHint')}</p>
        </div>
        <div>
          <label htmlFor="llm-num-ctx-vision" className={labelClass}>
            {t('config.llmContextWindowVision')}
          </label>
          <input
            id="llm-num-ctx-vision"
            type="number"
            min="1"
            step="1"
            value={config.llm_num_ctx_vision || ''}
            onChange={(e) => handleChange('llm_num_ctx_vision', e.target.value)}
            placeholder="32768"
            className="w-40 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-500"
          />
          <p className={hintClass}>{t('config.llmContextWindowVisionHint')}</p>
        </div>
      </div>
    </div>
  )
}
