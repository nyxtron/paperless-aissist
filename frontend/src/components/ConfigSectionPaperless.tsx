import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { documentsApi } from '../api/client'
import { Server, RefreshCw, CheckCircle, XCircle } from 'lucide-react'
import { ConfigSectionProps } from './ConfigSectionProps'
import { fieldClass, labelClass, hintClass } from './fieldStyles'

interface PaperlessTag {
  id: number
  name: string
}

interface PaperlessItem {
  id: number
  name: string
}

interface PaperlessStatus {
  connected: boolean
  error: string | null
  tags: PaperlessTag[]
  correspondents: PaperlessItem[]
}

export function ConfigSectionPaperless({ config, onSave, secretsSet }: ConfigSectionProps) {
  const { t } = useTranslation()
  const [testing, setTesting] = useState(false)
  const [status, setStatus] = useState<PaperlessStatus>({
    connected: false,
    error: null,
    tags: [],
    correspondents: [],
  })
  const [lastLoadedAt, setLastLoadedAt] = useState<string | null>(null)
  const hasPaperlessToken = secretsSet?.includes('paperless_token') ?? false

  const handleTest = useCallback(async () => {
    setTesting(true)
    setStatus((prev) => ({ ...prev, error: null }))
    try {
      const res = await documentsApi.getTags(true)
      setStatus({
        connected: true,
        error: null,
        tags: res.data.tags || [],
        correspondents: res.data.correspondents || [],
      })
      setLastLoadedAt(new Date().toLocaleString())
    } catch (error: unknown) {
      const errorMsg =
        error instanceof Error && 'response' in error
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail ||
            error.message
          : error instanceof Error
            ? error.message
            : 'Unknown error'
      const i18nKey = 'config.paperlessNotConfigured'
      const translatedMsg =
        errorMsg === 'Paperless URL and Token must be configured' ? t(i18nKey) : errorMsg
      setStatus((prev) => ({
        ...prev,
        connected: false,
        error: translatedMsg,
      }))
    } finally {
      setTesting(false)
    }
  }, [t])

  const handleChange = async (key: string, value: string) => {
    await onSave(key, value)
  }

  const getTagOptions = (savedValue: string) => {
    if (status.tags.length > 0) {
      return status.tags
    }
    if (savedValue) {
      return [{ id: -1, name: savedValue }]
    }
    return []
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow dark:shadow-none p-6 space-y-4">
      <div className="flex items-center gap-2 border-b border-gray-200 dark:border-gray-700 pb-3 mb-4">
        <Server size={18} className="text-blue-600 dark:text-blue-400" />
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100">{t('config.paperlessSection')}</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>{t('config.paperlessUrl')}</label>
          <input
            type="text"
            value={config.paperless_url || ''}
            onChange={(e) => handleChange('paperless_url', e.target.value)}
            placeholder="http://localhost:8000"
            className={fieldClass}
          />
        </div>
        <div>
          <label className={labelClass}>{t('config.apiToken')}</label>
          <input
            type="password"
            value={config.paperless_token || ''}
            onChange={(e) => handleChange('paperless_token', e.target.value)}
            placeholder={
              hasPaperlessToken
                ? t('config.alreadySetPlaceholder')
                : t('config.apiTokenPlaceholder')
            }
            className={fieldClass}
          />
        </div>
      </div>

      <div>
        <button
          onClick={handleTest}
          disabled={testing}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {testing ? <RefreshCw size={16} className="animate-spin" /> : <Server size={16} />}
          {testing ? t('config.connecting') : t('config.connect')}
        </button>
      </div>

      {status.connected && (
        <div className="space-y-1 rounded-lg bg-green-50 dark:bg-green-900/40 px-3 py-2 text-sm text-green-700 dark:text-green-300">
          <div className="flex items-center gap-2">
            <CheckCircle size={16} />
            {t('config.connectedBadge', {
              tags: status.tags.length,
              correspondents: status.correspondents.length,
            })}
          </div>
          {lastLoadedAt && (
            <div className="pl-6 text-xs text-green-800 dark:text-green-300">
              {t('config.lastLoaded', { time: lastLoadedAt })}
            </div>
          )}
        </div>
      )}

      {status.error && (
        <div className="flex items-center gap-2 px-3 py-2 bg-red-50 dark:bg-red-900/40 text-red-700 dark:text-red-300 rounded-lg text-sm">
          <XCircle size={16} />
          {status.error}
        </div>
      )}

      <div className="border-t border-gray-200 dark:border-gray-700 pt-4 space-y-4">
        {!lastLoadedAt && status.tags.length === 0 && (
          <p className="rounded-lg bg-blue-50 dark:bg-blue-900/40 px-3 py-2 text-sm text-blue-700 dark:text-blue-300">
            {t('config.notConnectedHint')}
          </p>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={labelClass}>{t('config.processTag')}</label>
            <select
              value={config.process_tag || ''}
              onChange={(e) => handleChange('process_tag', e.target.value)}
              className={fieldClass}
            >
              <option value="">{t('common.selectTag')}</option>
              {getTagOptions(config.process_tag).map((tag) => (
                <option key={tag.id} value={tag.name}>
                  {tag.name}
                </option>
              ))}
            </select>
            <p className={hintClass}>{t('config.processTagHint')}</p>
          </div>
          <div>
            <label className={labelClass}>{t('config.processedTag')}</label>
            <select
              value={config.processed_tag || ''}
              onChange={(e) => handleChange('processed_tag', e.target.value)}
              className={fieldClass}
            >
              <option value="">{t('common.selectTag')}</option>
              {getTagOptions(config.processed_tag).map((tag) => (
                <option key={tag.id} value={tag.name}>
                  {tag.name}
                </option>
              ))}
            </select>
            <p className={hintClass}>{t('config.processedTagHint')}</p>
          </div>
        </div>

        <div>
          <label className={labelClass}>{t('config.tagBlacklist')}</label>
          <input
            type="text"
            value={config.tag_blacklist || ''}
            onChange={(e) => handleChange('tag_blacklist', e.target.value)}
            placeholder={t('config.tagBlacklistPlaceholder')}
            className={fieldClass}
          />
          <p className={hintClass}>{t('config.tagBlacklistHint')}</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={labelClass}>{t('config.forceOcrTag')}</label>
            <select
              value={config.force_ocr_tag || ''}
              onChange={(e) => handleChange('force_ocr_tag', e.target.value)}
              className={fieldClass}
            >
              <option value="">{t('common.none')}</option>
              {getTagOptions(config.force_ocr_tag).map((tag) => (
                <option key={tag.id} value={tag.name}>
                  {tag.name}
                </option>
              ))}
            </select>
            <p className={hintClass}>{t('config.forceOcrTagHint')}</p>
          </div>
          <div>
            <label className={labelClass}>{t('config.forceOcrFixTag')}</label>
            <select
              value={config.force_ocr_fix_tag || ''}
              onChange={(e) => handleChange('force_ocr_fix_tag', e.target.value)}
              className={fieldClass}
            >
              <option value="">{t('common.none')}</option>
              {getTagOptions(config.force_ocr_fix_tag).map((tag) => (
                <option key={tag.id} value={tag.name}>
                  {tag.name}
                </option>
              ))}
            </select>
            <p className={hintClass}>{t('config.forceOcrFixTagHint')}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
