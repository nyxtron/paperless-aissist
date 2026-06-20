import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Copy, KeyRound, RotateCcw, Settings, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { configApi } from '../api/client'
import { ConfigSectionProps } from './ConfigSectionProps'
import { fieldClass, labelClass, hintClass } from './fieldStyles'

const AUTOMATION_TOKEN_SECRET_KEY = 'automation_api_token_hash'

async function copyTextToClipboard(text: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // Fall through to the legacy copy path for non-secure origins or denied clipboard access.
    }
  }

  if (typeof document.execCommand !== 'function') {
    return false
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.top = '-1000px'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()

  try {
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    document.body.removeChild(textarea)
  }
}

export function ConfigSectionAdvanced({
  config,
  onSave,
  secretsSet = [],
  onSecretsChanged,
}: ConfigSectionProps) {
  const { t } = useTranslation()
  const [automationToken, setAutomationToken] = useState('')
  const [automationBusy, setAutomationBusy] = useState(false)
  const [copied, setCopied] = useState(false)

  const hasAutomationToken = secretsSet.includes(AUTOMATION_TOKEN_SECRET_KEY)

  const handleChange = async (key: string, value: string) => {
    await onSave(key, value)
  }

  const handleGenerateAutomationToken = async () => {
    setAutomationBusy(true)
    setCopied(false)
    try {
      const response = await configApi.generateAutomationToken()
      setAutomationToken(response.data.token)
      onSecretsChanged?.()
    } catch (error) {
      console.error('Failed to generate automation token:', error)
      toast.error(t('config.automationTokenActionFailed'))
    } finally {
      setAutomationBusy(false)
    }
  }

  const handleRevokeAutomationToken = async () => {
    setAutomationBusy(true)
    setCopied(false)
    try {
      await configApi.revokeAutomationToken()
      setAutomationToken('')
      onSecretsChanged?.()
    } catch (error) {
      console.error('Failed to revoke automation token:', error)
      toast.error(t('config.automationTokenActionFailed'))
    } finally {
      setAutomationBusy(false)
    }
  }

  const handleCopyAutomationToken = async () => {
    if (!automationToken) return
    setCopied(false)
    const copiedToken = await copyTextToClipboard(automationToken)
    if (copiedToken) {
      setCopied(true)
    } else {
      toast.error(t('config.copyAutomationTokenFailed'))
    }
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
        <div className="w-48">
          <label className={labelClass}>{t('config.mcpEnabled')}</label>
          <select
            value={config.mcp_enabled || 'false'}
            onChange={(e) => handleChange('mcp_enabled', e.target.value)}
            className={fieldClass}
          >
            <option value="false">{t('common.disabled')}</option>
            <option value="true">{t('common.enabled')}</option>
          </select>
          <p className={hintClass}>{t('config.mcpEnabledHint')}</p>
        </div>
        <div className="w-64">
          <label htmlFor="document-list-refresh-mode" className={labelClass}>
            {t('config.documentListRefreshMode')}
          </label>
          <select
            id="document-list-refresh-mode"
            value={config.document_list_refresh_mode || 'automatic'}
            onChange={(e) => handleChange('document_list_refresh_mode', e.target.value)}
            className={fieldClass}
          >
            <option value="automatic">{t('config.documentListRefreshAutomatic')}</option>
            <option value="manual">{t('config.documentListRefreshManual')}</option>
          </select>
          <p className={hintClass}>{t('config.documentListRefreshModeHint')}</p>
        </div>
        <div className="w-48">
          <label htmlFor="ocr-fix-max-chars" className={labelClass}>
            {t('config.ocrFixMaxChars')}
          </label>
          <input
            id="ocr-fix-max-chars"
            type="number"
            min="1"
            value={config.ocr_fix_max_chars || '10000'}
            onChange={(e) => handleChange('ocr_fix_max_chars', e.target.value)}
            className={fieldClass}
          />
          <p className={hintClass}>{t('config.ocrFixMaxCharsHint')}</p>
        </div>
        <div className="md:col-span-2 border-t pt-4 mt-2">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <KeyRound size={16} className="text-blue-600" />
                <h3 className="text-sm font-semibold text-gray-800">
                  {t('config.automationApi')}
                </h3>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    hasAutomationToken || automationToken
                      ? 'bg-green-50 text-green-700 border border-green-200'
                      : 'bg-gray-100 text-gray-600 border border-gray-200'
                  }`}
                >
                  {hasAutomationToken || automationToken
                    ? t('config.automationTokenConfigured')
                    : t('config.automationTokenNotConfigured')}
                </span>
              </div>
              <p className={hintClass}>{t('config.automationApiHint')}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={handleGenerateAutomationToken}
                disabled={automationBusy}
                className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
              >
                <RotateCcw size={16} />
                {automationBusy
                  ? t('config.automationTokenWorking')
                  : t('config.generateAutomationToken')}
              </button>
              {(hasAutomationToken || automationToken) && (
                <button
                  type="button"
                  onClick={handleRevokeAutomationToken}
                  disabled={automationBusy}
                  className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200 disabled:opacity-50"
                >
                  <Trash2 size={16} />
                  {t('config.revokeAutomationToken')}
                </button>
              )}
            </div>
          </div>
          {automationToken && (
            <div className="mt-3 flex flex-col gap-2 sm:flex-row">
              <input
                readOnly
                value={automationToken}
                className={`${fieldClass} font-mono text-sm`}
                aria-label={t('config.automationToken')}
              />
              <button
                type="button"
                onClick={handleCopyAutomationToken}
                className="inline-flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200"
              >
                {copied ? <Check size={16} /> : <Copy size={16} />}
                {copied ? t('config.copiedAutomationToken') : t('config.copyAutomationToken')}
              </button>
            </div>
          )}
          {automationToken && (
            <p className="mt-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1.5">
              {t('config.automationTokenShownOnce')}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
