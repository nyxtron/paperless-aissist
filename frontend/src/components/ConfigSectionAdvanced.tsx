import { useTranslation } from 'react-i18next';
import { Settings } from 'lucide-react';

interface ConfigSectionProps {
  config: Record<string, string>;
  onSave: (key: string, value: string) => Promise<void>;
  onTest?: (key: string) => Promise<boolean>;
}

export function ConfigSectionAdvanced({ config, onSave }: ConfigSectionProps) {
  const { t } = useTranslation();

  const field = 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500';
  const label = 'block text-sm font-medium text-gray-700 mb-1';
  const hint = 'text-xs text-gray-500 mt-1';

  const handleChange = async (key: string, value: string) => {
    await onSave(key, value);
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center gap-2 border-b pb-3 mb-4">
        <Settings size={18} className="text-blue-600" />
        <h2 className="text-lg font-semibold text-gray-800">{t('config.applicationSection')}</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="w-48">
          <label className={label}>{t('config.logLevel')}</label>
          <select
            value={config.log_level || 'INFO'}
            onChange={(e) => handleChange('log_level', e.target.value)}
            className={field}
          >
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
          <p className={hint}>{t('config.logLevelHint')}</p>
        </div>
        <div className="w-48">
          <label className={label}>{t('config.authEnabled')}</label>
          <select
            value={config.auth_enabled || 'false'}
            onChange={(e) => handleChange('auth_enabled', e.target.value)}
            className={field}
          >
            <option value="false">{t('common.disabled')}</option>
            <option value="true">{t('common.enabled')}</option>
          </select>
          <p className={hint}>{t('config.authEnabledHint')}</p>
          {config.auth_enabled === 'true' && (
            <p className="mt-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1.5">
              {t('config.authEnabledWarning')}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
