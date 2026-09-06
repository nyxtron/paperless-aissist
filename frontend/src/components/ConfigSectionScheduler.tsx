import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { schedulerApi } from '../api/client'
import { Clock, Play, Square, RefreshCw, CheckCircle, XCircle } from 'lucide-react'
import { SchedulerStatus } from '../api/types'
import { buildPaperlessDocumentUrl } from '../utils/paperlessLinks'

interface SchedulerConfigSectionProps {
  config: Record<string, string>
  onSave: (key: string, value: string) => Promise<void>
}

export function ConfigSectionScheduler({
  config,
  onSave: _onSave,
}: SchedulerConfigSectionProps) {
  const { t } = useTranslation()
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus | null>(null)
  const [schedulerInterval, setSchedulerInterval] = useState(5)
  const [schedulerLoading, setSchedulerLoading] = useState(false)

  const label = 'block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1'
  const currentDocumentIds = schedulerStatus?.current_document_ids || []

  const loadSchedulerStatus = useCallback(async () => {
    try {
      const res = await schedulerApi.getStatus()
      setSchedulerStatus(res.data)
      if (res.data.interval_minutes) {
        setSchedulerInterval(res.data.interval_minutes)
      }
    } catch (error) {
      console.error('Failed to load scheduler status:', error)
    }
  }, [])

  useEffect(() => {
    loadSchedulerStatus()
  }, [loadSchedulerStatus])

  const handleSchedulerStart = async () => {
    setSchedulerLoading(true)
    try {
      await schedulerApi.start(schedulerInterval)
      await loadSchedulerStatus()
    } catch (error) {
      console.error('Failed to start scheduler:', error)
      toast.error(t('config.schedulerStartFailed'))
    } finally {
      setSchedulerLoading(false)
    }
  }

  const handleSchedulerStop = async () => {
    setSchedulerLoading(true)
    try {
      await schedulerApi.stop()
      await loadSchedulerStatus()
    } catch (error) {
      console.error('Failed to stop scheduler:', error)
      toast.error(t('config.schedulerStopFailed'))
    } finally {
      setSchedulerLoading(false)
    }
  }

  const handleClearState = async () => {
    if (!window.confirm(t('config.clearStateConfirm'))) return
    try {
      await schedulerApi.clearState()
      await loadSchedulerStatus()
      toast.success(t('config.clearStateSuccess'))
    } catch (error) {
      console.error('Failed to clear state:', error)
      toast.error(t('config.clearStateFailed'))
    }
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow dark:shadow-none p-6 space-y-6">
      <div className="flex items-center justify-between border-b border-gray-200 dark:border-gray-700 pb-3 mb-4">
        <div className="flex items-center gap-2">
          <Clock size={18} className="text-blue-600 dark:text-blue-400" />
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100">{t('config.schedulerSection')}</h2>
          {schedulerStatus?.running ? (
            <span className="flex items-center gap-1 px-2 py-1 bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 text-xs rounded-full">
              <CheckCircle size={11} /> {t('config.schedulerRunning')}
            </span>
          ) : (
            <span className="flex items-center gap-1 px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 text-xs rounded-full">
              <XCircle size={11} /> {t('config.schedulerStopped')}
            </span>
          )}
          {schedulerStatus?.is_processing && (
            <span className="flex items-center gap-1 px-2 py-1 bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 text-xs rounded-full">
              <RefreshCw size={11} className="animate-spin" /> {t('config.schedulerProcessing')}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-end gap-4">
        <div>
          <label className={label}>{t('config.schedulerInterval')}</label>
          <input
            type="number"
            min="1"
            max="60"
            value={schedulerInterval}
            onChange={(e) => setSchedulerInterval(parseInt(e.target.value) || 5)}
            disabled={schedulerStatus?.running}
            className="w-32 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-gray-100 disabled:bg-gray-100 dark:disabled:bg-gray-800"
          />
        </div>
        <div className="flex gap-2">
          {schedulerStatus?.running ? (
            <button
              onClick={handleSchedulerStop}
              disabled={schedulerLoading}
              className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
            >
              <Square size={16} />
              {t('config.stop')}
            </button>
          ) : (
            <button
              onClick={handleSchedulerStart}
              disabled={schedulerLoading}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
            >
              <Play size={16} />
              {t('config.start')}
            </button>
          )}
        </div>
        {schedulerStatus?.running && schedulerStatus.next_run && (
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {t('config.schedulerNextRun', {
              time: new Date(schedulerStatus.next_run).toLocaleString(),
            })}
          </span>
        )}
      </div>

      {schedulerStatus?.is_processing && currentDocumentIds.length > 0 && (
        <div className="text-sm text-blue-600 dark:text-blue-400">
          {currentDocumentIds.map((documentId, index) => {
            const currentDocumentUrl = buildPaperlessDocumentUrl(
              config.paperless_url || schedulerStatus?.paperless_url,
              documentId,
            )
            const label = t('config.schedulerCurrentDoc', { id: documentId })
            return (
              <span key={documentId}>
                {index > 0 && <span className="mx-1">·</span>}
                {currentDocumentUrl ? (
                  <a
                    href={currentDocumentUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="underline"
                  >
                    {label}
                  </a>
                ) : (
                  label
                )}
              </span>
            )
          })}
        </div>
      )}

      <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
        <button
          onClick={handleClearState}
          className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 underline"
        >
          {t('config.clearStuckState')}
        </button>
      </div>
    </div>
  )
}
