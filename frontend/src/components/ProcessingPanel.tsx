import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Play, RefreshCw, FileText, CheckCircle, XCircle, Clock, AlertTriangle } from 'lucide-react'
import { toast } from 'sonner'

import { configApi, documentsApi, schedulerApi } from '../api/client'
import { SchedulerStatus } from '../api/types'
import {
  getCachedDocumentList,
  invalidateDocumentListCache,
  loadCachedDocumentList,
  setCachedDocumentList,
} from '../utils/documentListCache'
import { buildPaperlessDocumentUrl } from '../utils/paperlessLinks'

interface TaggedDocument {
  id: number
  title: string | null
  created: string
  added: string
  tags: number[]
  tag_names?: string[]
  paperless_url?: string | null
}

type DocumentListRefreshMode = 'automatic' | 'manual'

export function clearProcessingDocumentCacheForTests() {
  invalidateDocumentListCache('processing')
}

interface ProcessingStep {
  name: string
  status: string
  duration_ms: number
  error?: string
  details?: {
    created_date?: string | null
    confidence?: string
    evidence?: string
    reason?: string
    [key: string]: unknown
  }
}

interface ProcessingResult {
  success: boolean
  document_id: number
  title: string
  updates: {
    title?: string
    correspondent?: number
    document_type?: number
    tags?: number[]
    custom_fields?: Array<{ field: number; value: string }>
    content?: string
    [key: string]: unknown
  }
  processing_time_ms: number
  steps: ProcessingStep[]
  proposed_changes: {
    title?: string
    correspondent?: { id: number; name: string }
    document_type?: { id: number; name: string }
    tags?: Array<{ id: number; name: string }>
    custom_fields?: Array<{ id: number; name: string; value: string }>
    content?: string
  }
  error?: string
}

interface TriggerProcessingResult {
  processed: number
  results?: Array<{
    success?: boolean
    document_id?: number
  }>
}

export default function ProcessingPanel() {
  const { t } = useTranslation()
  const [documents, setDocuments] = useState<TaggedDocument[]>([])
  const [loading, setLoading] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [processingId, setProcessingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ProcessingResult | null>(null)
  const [showResult, setShowResult] = useState(false)
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus | null>(null)
  const [paperlessUrl, setPaperlessUrl] = useState<string | null>(null)
  const [resultStepFilter, setResultStepFilter] = useState<'all' | 'failed' | 'completed'>('all')
  const [refreshMode, setRefreshMode] = useState<DocumentListRefreshMode>('automatic')
  const [hasLoadedDocuments, setHasLoadedDocuments] = useState(
    getCachedDocumentList<TaggedDocument>('processing') !== null,
  )

  const loadDocuments = useCallback(async (options: { force?: boolean } = {}) => {
    setLoading(true)
    setError(null)
    try {
      const loadedDocuments = await loadCachedDocumentList<TaggedDocument>(
        'processing',
        async () => {
          const res = await documentsApi.getTagged()
          if (res.data.error) {
            setError(res.data.error)
          }
          const responsePaperlessUrl = res.data.paperless_url || null
          setPaperlessUrl(responsePaperlessUrl)
          return (res.data.documents || []).map((doc: TaggedDocument) => ({
            ...doc,
            paperless_url: responsePaperlessUrl,
          }))
        },
        options,
      )
      const cachedPaperlessUrl = loadedDocuments.find((doc) => doc.paperless_url)?.paperless_url
      if (cachedPaperlessUrl) {
        setPaperlessUrl(cachedPaperlessUrl)
      }
      setDocuments(loadedDocuments)
      setHasLoadedDocuments(true)
    } catch (err: unknown) {
      const message = err instanceof Error && 'response' in err
        ? (err as { response?: { data?: { detail?: string; status?: number } } }).response?.data?.detail || (err instanceof Error ? err.message : 'Unknown error')
        : err instanceof Error ? err.message : String(err)
      setError(message)
      setDocuments([])
    } finally {
      setLoading(false)
    }
  }, [])

  const loadSchedulerStatus = async () => {
    try {
      const res = await schedulerApi.getStatus()
      setSchedulerStatus(res.data)
    } catch (error) {
      console.error('Failed to load scheduler status:', error)
    }
  }

  useEffect(() => {
    let mounted = true

    const loadRefreshMode = async () => {
      let mode: DocumentListRefreshMode = 'automatic'
      try {
        const res = await configApi.get('document_list_refresh_mode')
        mode = res.data.value === 'manual' ? 'manual' : 'automatic'
      } catch {
        mode = 'automatic'
      }

      if (!mounted) return

      setRefreshMode(mode)
      const cached = getCachedDocumentList<TaggedDocument>('processing')
      if (cached !== null) {
        setDocuments(cached)
        const cachedPaperlessUrl = cached.find((doc) => doc.paperless_url)?.paperless_url
        if (cachedPaperlessUrl) {
          setPaperlessUrl(cachedPaperlessUrl)
        }
        setHasLoadedDocuments(true)
      }
      if (mode === 'automatic') {
        loadDocuments()
      }
    }

    loadRefreshMode()
    loadSchedulerStatus()

    const interval = setInterval(loadSchedulerStatus, 2000)
    return () => {
      mounted = false
      clearInterval(interval)
    }
  }, [loadDocuments])

  const handleProcessAll = async () => {
    setProcessing(true)
    try {
      const res = await documentsApi.trigger()
      const data = res.data as TriggerProcessingResult
      toast.success(t('processing.processedCount', { count: data.processed }))
      const processedIds = new Set(
        (data.results || [])
          .filter((item) => item.success && typeof item.document_id === 'number')
          .map((item) => item.document_id as number),
      )
      if (processedIds.size > 0) {
        setDocuments((currentDocuments) => {
          const nextDocuments = currentDocuments.filter((doc) => !processedIds.has(doc.id))
          setCachedDocumentList('processing', nextDocuments)
          return nextDocuments
        })
      } else if (data.processed > 0) {
        invalidateDocumentListCache('processing')
      }
      loadSchedulerStatus()
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } }
      if (axiosErr.response?.status === 409) {
        toast.error(axiosErr.response?.data?.detail || t('processing.alreadyProcessing'))
      } else {
        toast.error(`Error: ${axiosErr.response?.data?.detail || (err instanceof Error ? err.message : String(err))}`)
      }
    } finally {
      setProcessing(false)
    }
  }

  const handleProcessOne = async (docId: number) => {
    setProcessingId(docId)
    setShowResult(false)
    setResult(null)
    try {
      const res = await documentsApi.process(docId)
      setResult(res.data)
      setShowResult(true)
      loadDocuments({ force: true })
      loadSchedulerStatus()
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      toast.error(`Error: ${axiosErr.response?.data?.detail || (err instanceof Error ? err.message : String(err))}`)
    } finally {
      setProcessingId(null)
    }
  }

  const formatDuration = (ms: number): string => {
    if (ms < 1000) return `${ms}ms`
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
    return `${(ms / 60000).toFixed(1)}m`
  }

  const formatStepDetails = (step: ProcessingStep): string | null => {
    const details = step.details
    if (!details) return null

    const parts: string[] = []
    if (details.created_date) parts.push(`created_date: ${details.created_date}`)
    if (details.confidence) parts.push(`confidence: ${details.confidence}`)
    if (details.reason) parts.push(`reason: ${details.reason}`)
    if (details.evidence) parts.push(`evidence: ${details.evidence}`)

    return parts.length > 0 ? parts.join(' · ') : null
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle size={14} className="text-green-500" />
      case 'failed':
        return <XCircle size={14} className="text-red-500" />
      default:
        return <Clock size={14} className="text-yellow-500" />
    }
  }

  const isCurrentlyProcessing = schedulerStatus?.is_processing || processing
  const currentDocumentIds = schedulerStatus?.current_document_ids || []
  const filteredSteps =
    resultStepFilter === 'all'
      ? result?.steps || []
      : (result?.steps || []).filter((step) => step.status === resultStepFilter)

  return (
    <div className="space-y-6">
      {isCurrentlyProcessing && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-center gap-3">
          <RefreshCw size={20} className="animate-spin text-blue-600" />
          <div>
            <span className="font-medium text-blue-700">
              {t('processing.processingInProgress')}
            </span>
            {(schedulerStatus?.active_documents || []).map((active) =>
              active.trigger_tags?.length ? (
                <span key={`tags-${active.document_id}`} className="ml-2">
                  {active.trigger_tags.map((tag) => (
                    <span
                      key={tag}
                      className="ml-1 rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-700"
                    >
                      {tag}
                    </span>
                  ))}
                </span>
              ) : null,
            )}
            {currentDocumentIds.map((documentId) => {
              const currentDocumentUrl = buildPaperlessDocumentUrl(
                schedulerStatus?.paperless_url || paperlessUrl,
                documentId,
              )
              const label = t('processing.currentDoc', { id: documentId })
              return currentDocumentUrl ? (
                <a
                  key={documentId}
                  href={currentDocumentUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-600 text-sm ml-2 underline"
                >
                  {label}
                </a>
              ) : (
                <span key={documentId} className="text-blue-600 text-sm ml-2">
                  {label}
                </span>
              )
            })}
          </div>
        </div>
      )}

      {schedulerStatus?.running && !schedulerStatus.is_processing && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-3 flex items-center gap-2 text-sm text-green-700">
          <Clock size={16} />
          <span>
            {t('processing.schedulerRunning', { minutes: schedulerStatus.interval_minutes })}
          </span>
          {schedulerStatus.next_run && (
            <span className="text-green-600 ml-2">
              {t('processing.schedulerNext', {
                time: new Date(schedulerStatus.next_run).toLocaleTimeString(),
              })}
            </span>
          )}
        </div>
      )}

      {schedulerStatus?.last_stop && !schedulerStatus.is_processing && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle size={16} />
            <span>{t('processing.runStoppedTitle')}</span>
            <span className="font-normal text-amber-700">
              {new Date(schedulerStatus.last_stop.at).toLocaleString()}
            </span>
          </div>
          <p className="mt-1">
            {t('processing.runStoppedBody', {
              failures: schedulerStatus.last_stop.failures,
              reason: schedulerStatus.last_stop.reason,
            })}
          </p>
        </div>
      )}

      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-lg font-semibold">{t('processing.sectionTitle')}</h2>
          <p className="text-sm text-gray-500">{t('processing.sectionSubtitle')}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => loadDocuments({ force: true })}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50"
          >
            <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
            {t('common.refresh')}
          </button>
          <button
            onClick={handleProcessAll}
            disabled={isCurrentlyProcessing || documents.length === 0}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            <Play size={18} />
            {t('processing.processAll', { count: documents.length })}
          </button>
        </div>
      </div>

      {error && <div className="p-4 bg-yellow-50 text-yellow-700 rounded-lg">{error}</div>}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <p className="text-xs text-gray-500 uppercase tracking-wide">{t('processing.queueCount')}</p>
          <p className="text-2xl font-semibold text-gray-900">{documents.length}</p>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <p className="text-xs text-gray-500 uppercase tracking-wide">{t('processing.schedulerState')}</p>
          <p className="text-sm font-medium text-gray-800">
            {schedulerStatus?.running ? t('config.schedulerRunning') : t('config.schedulerStopped')}
          </p>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <p className="text-xs text-gray-500 uppercase tracking-wide">{t('processing.schedulerNextLabel')}</p>
          <p className="text-sm font-medium text-gray-800">
            {schedulerStatus?.next_run
              ? new Date(schedulerStatus.next_run).toLocaleTimeString()
              : t('processing.notScheduled')}
          </p>
        </div>
      </div>

      {showResult && result && (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="bg-gray-50 px-4 py-3 border-b flex justify-between items-center">
            <h3 className="font-semibold text-gray-900">
              {t('processing.resultTitle', { id: result.document_id })}
            </h3>
            <button
              onClick={() => setShowResult(false)}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              {t('processing.hide')}
            </button>
          </div>
          <div className="p-4">
            <div className="flex items-center gap-2 mb-4">
              {result.success ? (
                <CheckCircle size={20} className="text-green-500" />
              ) : (
                <XCircle size={20} className="text-red-500" />
              )}
              <span className={result.success ? 'text-green-700' : 'text-red-700'}>
                {result.success ? t('processing.successMsg') : t('processing.failedMsg')}
              </span>
              <span className="text-gray-500 text-sm ml-2">
                ({formatDuration(result.processing_time_ms)})
              </span>
            </div>

            <div className="flex flex-wrap gap-2 mb-3">
              {(['all', 'failed', 'completed'] as const).map((status) => (
                <button
                  key={status}
                  onClick={() => setResultStepFilter(status)}
                  className={`text-xs px-2.5 py-1 rounded-full border ${
                    resultStepFilter === status
                      ? 'bg-blue-50 border-blue-300 text-blue-700'
                      : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  {status === 'all' ? t('dashboard.all') : t(`dashboard.${status}`)}
                </button>
              ))}
            </div>

            <div className="space-y-2">
              {filteredSteps.map((step, index) => (
                <div
                  key={index}
                  className={`flex items-start justify-between gap-3 px-3 py-2 rounded ${
                    step.status === 'completed'
                      ? 'bg-green-50'
                      : step.status === 'failed'
                        ? 'bg-red-50'
                        : 'bg-yellow-50'
                  }`}
                >
                  <div className="flex items-start gap-2 min-w-0">
                    <div className="mt-0.5">{getStatusIcon(step.status)}</div>
                    <div className="min-w-0">
                      <div>
                        <span className="text-sm text-gray-700">{step.name}</span>
                        {step.error && (
                          <span className="text-xs text-red-600 ml-2">- {step.error}</span>
                        )}
                      </div>
                      {formatStepDetails(step) && (
                        <p className="mt-1 text-xs text-gray-600 break-words">
                          {formatStepDetails(step)}
                        </p>
                      )}
                    </div>
                  </div>
                  <span className="text-xs text-gray-500">{formatDuration(step.duration_ms)}</span>
                </div>
              ))}
            </div>
            {filteredSteps.length === 0 && (
              <p className="text-sm text-gray-500">{t('processing.noStepsForFilter')}</p>
            )}

            {result.proposed_changes && Object.keys(result.proposed_changes).length > 0 && (
              <div className="mt-4 pt-4 border-t">
                <h4 className="text-sm font-medium text-gray-700 mb-2">
                  {t('processing.updatesApplied')}
                </h4>
                <div className="text-sm text-gray-600 space-y-1">
                  {result.proposed_changes.title && (
                    <div>
                      {t('processing.updateTitle')} {result.proposed_changes.title as string}
                    </div>
                  )}
                  {result.proposed_changes.correspondent && (
                    <div>
                      {t('processing.updateCorrespondent')}{' '}
                      {(result.proposed_changes.correspondent as { id: number; name: string }).name}
                    </div>
                  )}
                  {result.proposed_changes.document_type && (
                    <div>
                      {t('processing.updateDocType')}{' '}
                      {(result.proposed_changes.document_type as { id: number; name: string }).name}
                    </div>
                  )}
                  {result.proposed_changes.tags && (
                    <div>
                      {t('processing.updateTags')}{' '}
                      {JSON.stringify(
                        (result.proposed_changes.tags as Array<{ id: number; name: string }>).map(
                          (t) => t.name,
                        ),
                      )}
                    </div>
                  )}
                  {result.proposed_changes.custom_fields && (
                    <div>
                      {t('processing.updateCustomFields')}{' '}
                      {JSON.stringify(result.proposed_changes.custom_fields)}
                    </div>
                  )}
                  {result.proposed_changes.content && (
                    <div>
                      {t('processing.updateContent')}{' '}
                      {String(result.proposed_changes.content).substring(0, 100)}...
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-center py-8 text-gray-500">{t('common.loading')}</div>
      ) : refreshMode === 'manual' && !hasLoadedDocuments ? (
        <div className="bg-white rounded-lg border border-gray-200 text-center py-10 px-4 text-gray-500">
          <p className="font-medium text-gray-700 mb-1">{t('processing.manualRefreshTitle')}</p>
          <p className="text-sm">{t('processing.manualRefreshHint')}</p>
        </div>
      ) : documents.length === 0 ? (
        <div className="bg-white rounded-lg border border-gray-200 text-center py-10 px-4 text-gray-500">
          <p className="font-medium text-gray-700 mb-1">{t('processing.noDocuments')}</p>
          <p className="text-sm">{t('processing.noDocumentsHint')}</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">
                  {t('processing.colDocument')}
                </th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">
                  {t('processing.colTags')}
                </th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">
                  {t('processing.colId')}
                </th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">
                  {t('processing.colCreated')}
                </th>
                <th className="text-right py-3 px-4 text-sm font-medium text-gray-500">
                  {t('processing.colAction')}
                </th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => {
                const documentUrl = buildPaperlessDocumentUrl(
                  doc.paperless_url || paperlessUrl,
                  doc.id,
                )

                return (
                  <tr key={doc.id} className="border-t hover:bg-gray-50">
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <FileText size={18} className="text-gray-400" />
                        {documentUrl ? (
                          <a
                            href={documentUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="font-medium text-blue-700 hover:underline"
                          >
                            {doc.title || t('processing.docFallback', { id: doc.id })}
                            <span className="ml-2 text-xs text-gray-500">#{doc.id}</span>
                          </a>
                        ) : (
                          <span className="font-medium">
                            {doc.title || t('processing.docFallback', { id: doc.id })}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex flex-wrap gap-1">
                        {(doc.tag_names || []).map((tag) => (
                          <span
                            key={tag}
                            className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-gray-600">#{doc.id}</td>
                    <td className="py-3 px-4 text-gray-600">
                      {new Date(doc.created).toLocaleDateString()}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => handleProcessOne(doc.id)}
                        disabled={processingId !== null || isCurrentlyProcessing}
                        className="flex items-center gap-1 px-3 py-1 bg-green-600 text-white text-sm rounded hover:bg-green-700 disabled:opacity-50"
                      >
                        {processingId === doc.id ? (
                          <>
                            <RefreshCw size={14} className="animate-spin" />
                            {t('processing.processingBtn')}
                          </>
                        ) : (
                          <>
                            <Play size={14} />
                            {t('processing.processBtn')}
                          </>
                        )}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
