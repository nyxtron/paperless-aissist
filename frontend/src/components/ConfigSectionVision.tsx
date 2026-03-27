import { useTranslation } from 'react-i18next';

interface ConfigSectionProps {
  config: Record<string, string>;
  onSave: (key: string, value: string) => Promise<void>;
  onTest?: (key: string) => Promise<boolean>;
}

export function ConfigSectionVision({ config, onSave }: ConfigSectionProps) {
  const { t } = useTranslation();
  const field = 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500';
  const label = 'block text-sm font-medium text-gray-700 mb-1';
  const hint = 'text-xs text-gray-500 mt-1';

  const handleChange = async (key: string, value: string) => {
    await onSave(key, value);
  };

  const getVisionModelPlaceholder = (provider: string) => {
    if (provider === 'openai') return 'gpt-4o';
    if (provider === 'grok') return 'grok-2-vision-1212';
    return 'qwen2.5vl:7b';
  };

  const getApiBasePlaceholder = (provider: string) => {
    if (provider === 'openai') return 'https://api.openai.com/v1';
    if (provider === 'grok') return 'https://api.x.ai/v1';
    return 'http://localhost:11434';
  };

  const getApiKeyPlaceholder = (provider: string) => {
    if (provider === 'ollama') return t('config.apiKeyPlaceholderOllama');
    return t('config.apiKeyPlaceholderCloud');
  };

  return (
    <div className="bg-white rounded-lg shadow p-6 space-y-4">
      <div className="flex items-center gap-2 border-b pb-3 mb-4">
        <h3 className="text-sm font-semibold text-gray-700">{t('config.visionModelSection')}</h3>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className={label}>{t('config.provider')}</label>
          <select
            value={config.llm_provider_vision || 'ollama'}
            onChange={(e) => handleChange('llm_provider_vision', e.target.value)}
            className={field}
          >
            <option value="ollama">Ollama</option>
            <option value="openai">OpenAI</option>
            <option value="grok">Grok (xAI)</option>
          </select>
        </div>
        <div>
          <label className={label}>{t('config.visionModel')}</label>
          <input
            type="text"
            value={config.llm_model_vision || ''}
            onChange={(e) => handleChange('llm_model_vision', e.target.value)}
            placeholder={getVisionModelPlaceholder(config.llm_provider_vision)}
            className={field}
          />
        </div>
        <div>
          <label className={label}>{t('config.apiBaseUrl')}</label>
          <input
            type="text"
            value={config.llm_api_base_vision || ''}
            onChange={(e) => handleChange('llm_api_base_vision', e.target.value)}
            placeholder={getApiBasePlaceholder(config.llm_provider_vision)}
            className={field}
          />
        </div>
        <div>
          <label className={label}>
            {t('config.apiKey')} <span className="font-normal text-gray-400">({t('common.optional')})</span>
          </label>
          <input
            type="password"
            value={config.llm_api_key_vision || ''}
            onChange={(e) => handleChange('llm_api_key_vision', e.target.value)}
            placeholder={getApiKeyPlaceholder(config.llm_provider_vision)}
            className={field}
          />
          <p className={hint}>{t('config.apiKeyHint')}</p>
        </div>
        <div>
          <label className={label}>{t('config.llmTimeoutVision')}</label>
          <input
            type="number"
            min="30"
            max="3600"
            value={config.llm_timeout_vision || '600'}
            onChange={(e) => handleChange('llm_timeout_vision', e.target.value)}
            className="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
          />
          <p className={hint}>{t('config.llmTimeoutVisionHint')}</p>
        </div>
      </div>
    </div>
  );
}
