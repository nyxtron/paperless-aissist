import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { configApi, statsApi } from '../api/client'
import { RefreshCw, Trash2 } from 'lucide-react'
import { buildPaperlessDocumentUrl } from '../utils/paperlessLinks'
import { useTheme } from '../contexts/ThemeContext'

const COLORS = ['#22c55e', '#ef4444', '#f59e0b']

interface Stats {
  total_processed: number
  success: number
  failed: number
  skipped: number
  success_rate: number
  avg_processing_time_ms: number
}

interface DailyStats {
  date: string
  success: number
  failed: number
  skipped: number
}

interface RecentLog {
  id: number
  document_id: number
  document_title: string | null
  status: string
  llm_provider: string | null
  llm_model: string | null
  llm_response?: string | null
  error_message: string | null
  trigger_tags?: string | null
  processing_time_ms: number | null
  processed_at: string
}

export default function Dashboard() {
  const { t } = useTranslation()
  const { resolved } = useTheme()
  const [stats, setStats] = useState<Stats | null>(null)
  const [dailyStats, setDailyStats] = useState<DailyStats[]>([])
  const [recentLogs, setRecentLogs] = useState<RecentLog[]>([])
  const [loading, setLoading] = useState(true)
  const [resetting, setResetting] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [logFilter, setLogFilter] = useState<'all' | 'success' | 'failed' | 'skipped'>('all')
  const [paperlessUrl, setPaperlessUrl] = useState<string | null>(null)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      setLoadError(null)
      const [statsRes, dailyRes, recentRes, paperlessUrlRes] = await Promise.all([
        statsApi.get(),
        statsApi.getDaily(7),
        statsApi.getRecent(10),
        configApi.get('paperless_url').catch(() => ({ data: { value: null } })),
      ])
      setStats(statsRes.data)
      setDailyStats(dailyRes.data)
      setRecentLogs(recentRes.data)
      setPaperlessUrl(paperlessUrlRes.data.value || null)
    } catch (error) {
      const message = error instanceof Error ? error.message : t('dashboard.loadFailed')
      setLoadError(message)
      setStats(null)
      setDailyStats([])
      setRecentLogs([])
    } finally {
      setLoading(false)
    }
  }

  const handleReset = async () => {
    if (!window.confirm(t('dashboard.confirmReset'))) {
      return
    }
    setResetting(true)
    try {
      await statsApi.reset()
      loadData()
    } catch (error) {
      console.error('Failed to reset stats:', error)
      toast.error(t('dashboard.resetFailed'))
    } finally {
      setResetting(false)
    }
  }

  if (loading) {
    return <div className="py-8 text-gray-500 dark:text-gray-400">{t('common.loading')}</div>
  }

  const pieData = stats
    ? [
        { name: t('dashboard.success'), value: stats.success },
        { name: t('dashboard.failed'), value: stats.failed },
        { name: t('dashboard.skipped'), value: stats.skipped },
      ]
    : []

  const filteredLogs =
    logFilter === 'all' ? recentLogs : recentLogs.filter((log) => log.status === logFilter)

  const getDateStepDetails = (llmResponse?: string | null): string | null => {
    if (!llmResponse) return null
    try {
      const parsed = JSON.parse(llmResponse) as {
        steps?: Array<{
          name?: string
          details?: {
            created_date?: string | null
            confidence?: string
            evidence?: string
            reason?: string
          }
        }>
      }
      const dateStep = parsed.steps?.find((step) => step.name === 'date' && step.details)
      if (!dateStep?.details) return null

      const details = dateStep.details
      const parts: string[] = []
      if (details.created_date) parts.push(`created_date: ${details.created_date}`)
      if (details.confidence) parts.push(`confidence: ${details.confidence}`)
      if (details.reason) parts.push(`reason: ${details.reason}`)
      if (details.evidence) parts.push(`evidence: ${details.evidence}`)

      return parts.length > 0 ? parts.join(' · ') : null
    } catch {
      return null
    }
  }

  const chart = resolved === 'dark'
    ? { text: '#9ca3af', panel: '#1f2937', border: '#374151' }
    : { text: '#6b7280', panel: '#ffffff', border: '#e5e7eb' }
  const tooltipStyle = { backgroundColor: chart.panel, borderColor: chart.border, color: chart.text }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{t('dashboard.title')}</h1>
        <div className="flex gap-2">
          <button
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
          >
            <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
            {t('common.refresh')}
          </button>
          <button
            onClick={handleReset}
            disabled={resetting}
            className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-gray-800 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/40 disabled:opacity-50"
          >
            <Trash2 size={18} />
            {resetting ? t('dashboard.resetting') : t('dashboard.resetStats')}
          </button>
        </div>
      </div>

      {loadError && (
        <div className="p-4 bg-red-50 dark:bg-red-900/40 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-300 text-sm">
          {t('dashboard.loadFailed')}: {loadError}
        </div>
      )}

      {!loadError && !stats && (
        <div className="p-8 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 text-center text-gray-500 dark:text-gray-400">
          {t('dashboard.emptyState')}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow dark:shadow-none p-6">
          <p className="text-sm text-gray-500 dark:text-gray-400">{t('dashboard.totalProcessed')}</p>
          <p className="text-3xl font-bold text-gray-900 dark:text-gray-100">{stats?.total_processed || 0}</p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow dark:shadow-none p-6">
          <p className="text-sm text-gray-500 dark:text-gray-400">{t('dashboard.successRate')}</p>
          <p className="text-3xl font-bold text-green-600 dark:text-green-400">{stats?.success_rate || 0}%</p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow dark:shadow-none p-6">
          <p className="text-sm text-gray-500 dark:text-gray-400">{t('dashboard.avgProcessingTime')}</p>
          <p className="text-3xl font-bold text-gray-900 dark:text-gray-100">
            {((stats?.avg_processing_time_ms || 0) / 1000).toFixed(1)}s
          </p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow dark:shadow-none p-6">
          <p className="text-sm text-gray-500 dark:text-gray-400">{t('dashboard.failed')}</p>
          <p className="text-3xl font-bold text-red-600 dark:text-red-400">{stats?.failed || 0}</p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow dark:shadow-none p-6">
          <p className="text-sm text-gray-500 dark:text-gray-400">{t('dashboard.skipped')}</p>
          <p className="text-3xl font-bold text-amber-600 dark:text-amber-400">{stats?.skipped || 0}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow dark:shadow-none p-6">
          <h2 className="text-lg font-semibold mb-4 text-gray-900 dark:text-gray-100">{t('dashboard.processingStatus')}</h2>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={80}
                paddingAngle={2}
                dataKey="value"
              >
                {pieData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex justify-center gap-4 mt-4">
            {pieData.map((entry, index) => (
              <div key={entry.name} className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS[index] }} />
                <span className="text-sm text-gray-600 dark:text-gray-300">
                  {entry.name}: {entry.value}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow dark:shadow-none p-6">
          <h2 className="text-lg font-semibold mb-4 text-gray-900 dark:text-gray-100">{t('dashboard.dailyProcessing')}</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={dailyStats}>
              <XAxis dataKey="date" tick={{ fontSize: 12, fill: chart.text }} />
              <YAxis tick={{ fill: chart.text }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="success" fill="#22c55e" name={t('dashboard.success')} />
              <Bar dataKey="failed" fill="#ef4444" name={t('dashboard.failed')} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow dark:shadow-none p-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('dashboard.recentLogs')}</h2>
          <div className="flex flex-wrap gap-2">
            {(['all', 'success', 'failed', 'skipped'] as const).map((status) => (
              <button
                key={status}
                onClick={() => setLogFilter(status)}
                className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                  logFilter === status
                    ? 'bg-blue-50 dark:bg-blue-900/40 border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-300'
                    : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                }`}
              >
                {status === 'all' ? t('dashboard.all') : t(`dashboard.${status}`)}
              </button>
            ))}
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px]">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                  {t('dashboard.colDocument')}
                </th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                  {t('dashboard.colStatus')}
                </th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                  {t('dashboard.colModel')}
                </th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                  {t('dashboard.colTime')}
                </th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                  {t('dashboard.colDate')}
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredLogs.map((log) => {
                const documentUrl = buildPaperlessDocumentUrl(paperlessUrl, log.document_id)

                return (
                  <tr key={log.id} className="border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700">
                    <td className="py-3 px-4">
                      {documentUrl ? (
                        <a
                          href={documentUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="font-medium text-blue-700 dark:text-blue-300 hover:underline"
                        >
                          {log.document_title
                            || t('dashboard.docFallback', { id: log.document_id })}
                          <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">
                            #{log.document_id}
                          </span>
                        </a>
                      ) : (
                        <span>
                          {log.document_title
                            || t('dashboard.docFallback', { id: log.document_id })}
                          {log.document_id && (
                            <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">
                              #{log.document_id}
                            </span>
                          )}
                        </span>
                      )}
                      {log.trigger_tags && (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {log.trigger_tags.split(',').map((tag) => (
                            <span
                              key={tag}
                              className="rounded bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 text-xs text-gray-600 dark:text-gray-300"
                            >
                              {tag.trim()}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-1 rounded text-xs font-medium ${
                          log.status === 'success'
                            ? 'bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-300'
                            : log.status === 'failed'
                              ? 'bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-300'
                              : 'bg-yellow-100 dark:bg-yellow-900/40 text-yellow-800 dark:text-yellow-300'
                        }`}
                      >
                        {log.status}
                      </span>
                      {log.status === 'failed' && log.error_message && (
                        <p
                          className="mt-1 text-xs text-red-600 dark:text-red-400 max-w-xs truncate"
                          title={log.error_message}
                        >
                          {log.error_message}
                        </p>
                      )}
                      {getDateStepDetails(log.llm_response) && (
                        <p
                          className="mt-1 text-xs text-gray-600 dark:text-gray-300 max-w-sm truncate"
                          title={getDateStepDetails(log.llm_response) || undefined}
                        >
                          {getDateStepDetails(log.llm_response)}
                        </p>
                      )}
                    </td>
                    <td className="py-3 px-4 text-sm text-gray-600 dark:text-gray-300">{log.llm_model || '-'}</td>
                    <td className="py-3 px-4 text-sm text-gray-600 dark:text-gray-300">
                      {log.processing_time_ms
                        ? `${(log.processing_time_ms / 1000).toFixed(1)}s`
                        : '-'}
                    </td>
                    <td className="py-3 px-4 text-sm text-gray-600 dark:text-gray-300">
                      {new Date(log.processed_at).toLocaleString()}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {filteredLogs.length === 0 && (
          <p className="text-sm text-gray-500 dark:text-gray-400 py-4">{t('dashboard.noLogsForFilter')}</p>
        )}
      </div>
    </div>
  )
}
