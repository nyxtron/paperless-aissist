import { useTranslation } from 'react-i18next'
import { Settings } from 'lucide-react'
import { ConfigSectionProps } from './ConfigSectionProps'
import { fieldClass, labelClass, hintClass } from './fieldStyles'

export function ConfigSectionAdvanced({ config, onSave }: ConfigSectionProps) {
  const { t } = useTranslation()

  const handleChange = async (key: string, value: string) => {
    await onSave(key, value)
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center gap-2 border-b pb-3 mb-4">
        <Settings size={18} className="text-blue-600" />
        <h2 className="text-lg font-semibold text-gray-800">{t('config.applicationSection')}</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="w-48">
          <label className={labelClass}>{t('config.logLevel')}</label>
          <select
            value={config.log_level || 'INFO'}
            onChange={(e) => handleChange('log_level', e.target.value)}
            className={fieldClass}
          >
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
          <p className={hintClass}>{t('config.logLevelHint')}</p>
        </div>
        <div className="w-48">
          <label className={labelClass}>{t('config.authEnabled')}</label>
          <select
            value={config.auth_enabled || 'false'}
            onChange={(e) => handleChange('auth_enabled', e.target.value)}
            className={fieldClass}
          >
            <option value="false">{t('common.disabled')}</option>
            <option value="true">{t('common.enabled')}</option>
          </select>
          <p className={hintClass}>{t('config.authEnabledHint')}</p>
          {config.auth_enabled === 'true' && (
            <p className="mt-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1.5">
              {t('config.authEnabledWarning')}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
