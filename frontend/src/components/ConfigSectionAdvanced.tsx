import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Copy, KeyRound, RotateCcw, Settings, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { configApi } from '../api/client'
import { ConfigSectionProps } from './ConfigSectionProps'
import { fieldClass, labelClass, hintClass } from './fieldStyles'

// fieldStyles.ts is shared across several config sections and stays untouched here;
// these wrap the shared constants with the dark-mode variants for this file's fields.
const fieldClassDark = `${fieldClass} dark:bg-gray-900 dark:border-gray-600 dark:text-gray-100 dark:placeholder-gray-500`
const labelClassDark = `${labelClass} dark:text-gray-200`
const hintClassDark = `${hintClass} dark:text-gray-400`

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
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow dark:shadow-none p-6">
      <div className="flex items-center gap-2 border-b border-gray-200 dark:border-gray-700 pb-3 mb-4">
        <Settings size={18} className="text-blue-600 dark:text-blue-400" />
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100">{t('config.applicationSection')}</h2>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 max-w-4xl">
        <div>
          <label className={labelClassDark}>{t('config.logLevel')}</label>
          <select
            value={config.log_level || 'INFO'}
            onChange={(e) => handleChange('log_level', e.target.value)}
            className={fieldClassDark}
          >
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
          <p className={hintClassDark}>{t('config.logLevelHint')}</p>
        </div>
        <div>
          <label className={labelClassDark}>{t('config.authEnabled')}</label>
          <select
            value={config.auth_enabled || 'false'}
            onChange={(e) => handleChange('auth_enabled', e.target.value)}
            className={fieldClassDark}
          >
            <option value="false">{t('common.disabled')}</option>
            <option value="true">{t('common.enabled')}</option>
          </select>
          <p className={hintClassDark}>{t('config.authEnabledHint')}</p>
          {config.auth_enabled === 'true' && (
            <p className="mt-2 text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/40 border border-amber-200 dark:border-amber-800 rounded px-2 py-1.5">
              {t('config.authEnabledWarning')}
            </p>
          )}
        </div>
        <div>
          <label className={labelClassDark}>{t('config.mcpEnabled')}</label>
          <select
            value={config.mcp_enabled || 'false'}
            onChange={(e) => handleChange('mcp_enabled', e.target.value)}
            className={fieldClassDark}
          >
            <option value="false">{t('common.disabled')}</option>
            <option value="true">{t('common.enabled')}</option>
          </select>
          <p className={hintClassDark}>{t('config.mcpEnabledHint')}</p>
        </div>
        <div>
          <label htmlFor="correspondent-create-new" className={labelClassDark}>
            {t('config.correspondentCreateNew')}
          </label>
          <select
            id="correspondent-create-new"
            value={config.correspondent_create_new || 'false'}
            onChange={(e) => handleChange('correspondent_create_new', e.target.value)}
            className={fieldClassDark}
          >
            <option value="false">{t('common.disabled')}</option>
            <option value="true">{t('common.enabled')}</option>
          </select>
          <p className={hintClassDark}>{t('config.correspondentCreateNewHint')}</p>
          {config.correspondent_create_new === 'true' && (
            <p className="mt-2 text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/40 border border-amber-200 dark:border-amber-800 rounded px-2 py-1.5">
              {t('config.correspondentCreateNewWarning')}
            </p>
          )}
        </div>
        <div>
          <label htmlFor="correspondent-create-owner" className={labelClassDark}>
            {t('config.correspondentCreateOwner')}
          </label>
          <select
            id="correspondent-create-owner"
            value={config.correspondent_create_owner || 'api_user'}
            onChange={(e) => handleChange('correspondent_create_owner', e.target.value)}
            className={fieldClassDark}
          >
            <option value="api_user">{t('config.correspondentOwnerApiUser')}</option>
            <option value="none">{t('config.correspondentOwnerNone')}</option>
          </select>
          <p className={hintClassDark}>{t('config.correspondentCreateOwnerHint')}</p>
        </div>
        <div>
          <label htmlFor="correspondent-create-matching" className={labelClassDark}>
            {t('config.correspondentCreateMatching')}
          </label>
          <select
            id="correspondent-create-matching"
            value={config.correspondent_create_matching || ''}
            onChange={(e) => handleChange('correspondent_create_matching', e.target.value)}
            className={fieldClassDark}
          >
            <option value="">{t('config.matchingDefault')}</option>
            <option value="0">{t('config.matchingNone')}</option>
            <option value="1">{t('config.matchingAny')}</option>
            <option value="2">{t('config.matchingAll')}</option>
            <option value="3">{t('config.matchingLiteral')}</option>
            <option value="4">{t('config.matchingRegex')}</option>
            <option value="5">{t('config.matchingFuzzy')}</option>
            <option value="6">{t('config.matchingAuto')}</option>
          </select>
          <p className={hintClassDark}>{t('config.correspondentCreateMatchingHint')}</p>
        </div>
        <div>
          <label htmlFor="document-list-refresh-mode" className={labelClassDark}>
            {t('config.documentListRefreshMode')}
          </label>
          <select
            id="document-list-refresh-mode"
            value={config.document_list_refresh_mode || 'automatic'}
            onChange={(e) => handleChange('document_list_refresh_mode', e.target.value)}
            className={fieldClassDark}
          >
            <option value="automatic">{t('config.documentListRefreshAutomatic')}</option>
            <option value="manual">{t('config.documentListRefreshManual')}</option>
          </select>
          <p className={hintClassDark}>{t('config.documentListRefreshModeHint')}</p>
        </div>
        <div>
          <label htmlFor="ocr-fix-max-chars" className={labelClassDark}>
            {t('config.ocrFixMaxChars')}
          </label>
          <input
            id="ocr-fix-max-chars"
            type="number"
            min="1"
            value={config.ocr_fix_max_chars || '10000'}
            onChange={(e) => handleChange('ocr_fix_max_chars', e.target.value)}
            className={fieldClassDark}
          />
          <p className={hintClassDark}>{t('config.ocrFixMaxCharsHint')}</p>
        </div>
        <div>
          <label htmlFor="max-concurrent-processing" className={labelClassDark}>
            {t('config.maxConcurrentProcessing')}
          </label>
          <input
            id="max-concurrent-processing"
            type="number"
            min="1"
            value={config.max_concurrent_processing || '3'}
            onChange={(e) => handleChange('max_concurrent_processing', e.target.value)}
            className={fieldClassDark}
          />
          <p className={hintClassDark}>{t('config.maxConcurrentProcessingHint')}</p>
        </div>
        <div>
          <label htmlFor="max-consecutive-failures" className={labelClassDark}>
            {t('config.maxConsecutiveFailures')}
          </label>
          <input
            id="max-consecutive-failures"
            type="number"
            min="0"
            value={config.max_consecutive_failures || '3'}
            onChange={(e) => handleChange('max_consecutive_failures', e.target.value)}
            className={fieldClassDark}
          />
          <p className={hintClassDark}>{t('config.maxConsecutiveFailuresHint')}</p>
        </div>
        <div className="sm:col-span-2 lg:col-span-3 border-t border-gray-200 dark:border-gray-700 pt-4 mt-2">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <KeyRound size={16} className="text-blue-600 dark:text-blue-400" />
                <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                  {t('config.automationApi')}
                </h3>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    hasAutomationToken || automationToken
                      ? 'bg-green-50 dark:bg-green-900/40 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-800'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700'
                  }`}
                >
                  {hasAutomationToken || automationToken
                    ? t('config.automationTokenConfigured')
                    : t('config.automationTokenNotConfigured')}
                </span>
              </div>
              <p className={hintClassDark}>{t('config.automationApiHint')}</p>
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
                  className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-lg bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50"
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
                className={`${fieldClassDark} font-mono text-sm`}
                aria-label={t('config.automationToken')}
              />
              <button
                type="button"
                onClick={handleCopyAutomationToken}
                className="inline-flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium rounded-lg bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600"
              >
                {copied ? <Check size={16} /> : <Copy size={16} />}
                {copied ? t('config.copiedAutomationToken') : t('config.copyAutomationToken')}
              </button>
            </div>
          )}
          {automationToken && (
            <p className="mt-2 text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/40 border border-amber-200 dark:border-amber-800 rounded px-2 py-1.5">
              {t('config.automationTokenShownOnce')}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
