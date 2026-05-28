import { useTranslation } from 'react-i18next'
import { ConfigSectionProps } from './ConfigSectionProps'
import { fieldClass, labelClass, hintClass, sourceBadgeClass } from './fieldStyles'

export function ConfigSectionVision({ config, onSave, secretsSet, sources }: ConfigSectionProps) {
  const { t } = useTranslation()
  const visionEnabled = (config.enable_vision || 'false') === 'true'

  const handleChange = async (key: string, value: string) => {
    await onSave(key, value)
  }

  const renderSourceBadge = (key: string) => {
    const source = sources?.[key]
    if (!source) return null
    const envKey = key.toUpperCase().replace(/-/g, '_')
    return (
      <span
        title={
          source === 'env'
            ? t('config.sourceEnvTooltip', { key: envKey })
            : t('config.sourceUserTooltip', { key: envKey })
        }
        className={`ml-1.5 text-xs px-1.5 py-0.5 rounded font-normal cursor-help ${sourceBadgeClass(source)}`}
      >
        {source === 'env' ? t('config.sourceEnv') : t('config.sourceUser')}
      </span>
    )
  }

  const getVisionModelPlaceholder = (provider: string) => {
    if (provider === 'openai') return 'gpt-4o'
    if (provider === 'grok') return 'grok-2-vision-1212'
    return 'qwen2.5vl:7b'
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
    <div className="bg-blue-50/50 border border-blue-100 rounded-lg shadow-sm p-6 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-blue-100 pb-3 mb-4">
        <h3 className="text-sm font-semibold text-gray-800">{t('config.visionModelSection')}</h3>
        <span
          className={`text-xs px-2 py-1 rounded-full ${
            visionEnabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
          }`}
        >
          {visionEnabled ? t('common.enabled') : t('common.disabled')}
        </span>
      </div>
      {!visionEnabled && <p className={hintClass}>{t('config.visionSectionDisabledHint')}</p>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>
            {t('config.provider')}
            {renderSourceBadge('llm_provider_vision')}
          </label>
          <select
            value={config.llm_provider_vision || 'ollama'}
            onChange={(e) => handleChange('llm_provider_vision', e.target.value)}
            className={fieldClass}
          >
            <option value="ollama">Ollama</option>
            <option value="openai">OpenAI</option>
            <option value="grok">Grok (xAI)</option>
          </select>
        </div>
        <div>
          <label className={labelClass}>
            {t('config.visionModel')}
            {renderSourceBadge('llm_model_vision')}
          </label>
          <input
            type="text"
            value={config.llm_model_vision || ''}
            onChange={(e) => handleChange('llm_model_vision', e.target.value)}
            placeholder={getVisionModelPlaceholder(config.llm_provider_vision)}
            className={fieldClass}
          />
        </div>
        <div>
          <label className={labelClass}>
            {t('config.apiBaseUrl')}
            {renderSourceBadge('llm_api_base_vision')}
          </label>
          <input
            type="text"
            value={config.llm_api_base_vision || ''}
            onChange={(e) => handleChange('llm_api_base_vision', e.target.value)}
            placeholder={getApiBasePlaceholder(config.llm_provider_vision)}
            className={fieldClass}
          />
        </div>
        <div>
          <label className={labelClass}>
            {t('config.apiKey')}{' '}
            <span className="font-normal text-gray-400">({t('common.optional')})</span>
            {renderSourceBadge('llm_api_key_vision')}
          </label>
          <input
            type="password"
            value={config.llm_api_key_vision || ''}
            onChange={(e) => handleChange('llm_api_key_vision', e.target.value)}
            placeholder={
              secretsSet?.includes('llm_api_key_vision')
                ? t('config.alreadySetPlaceholder')
                : sources?.['llm_api_key_vision'] === 'env'
                  ? t('config.envSetPlaceholder')
                  : getApiKeyPlaceholder(config.llm_provider_vision)
            }
            className={fieldClass}
          />
          <p className={hintClass}>{t('config.apiKeyHint')}</p>
        </div>
      </div>

      <div className="border-t border-blue-100 pt-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">{t('config.visionLlmParams')}</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label htmlFor="vision-pdf-mode" className={labelClass}>
              {t('config.visionPdfMode')}
              {renderSourceBadge('vision_pdf_mode')}
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
              {t('config.llmTimeoutVision')}
              {renderSourceBadge('llm_timeout_vision')}
            </label>
            <input
              type="number"
              min="30"
              max="3600"
              value={config.llm_timeout_vision || '600'}
              onChange={(e) => handleChange('llm_timeout_vision', e.target.value)}
              className="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            />
            <p className={hintClass}>{t('config.llmTimeoutVisionHint')}</p>
          </div>
          <div>
            <label className={labelClass}>
              {t('config.temperature')}
              {renderSourceBadge('llm_temperature_vision')}
            </label>
            <input
              type="number"
              min="0"
              max="2"
              step="0.1"
              value={config.llm_temperature_vision || ''}
              onChange={(e) => handleChange('llm_temperature_vision', e.target.value)}
              placeholder="0.0"
              className="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            />
            <p className={hintClass}>{t('config.temperatureHint')}</p>
          </div>
          <div>
            <label className={labelClass}>
              {t('config.maxTokens')}
              {renderSourceBadge('llm_max_tokens_vision')}
            </label>
            <input
              type="number"
              min="1"
              step="1"
              value={config.llm_max_tokens_vision || ''}
              onChange={(e) => handleChange('llm_max_tokens_vision', e.target.value)}
              placeholder="4092"
              className="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            />
            <p className={hintClass}>{t('config.maxTokensHint')}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
