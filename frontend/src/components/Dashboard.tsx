import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { statsApi } from '../api/client';
import { RefreshCw, Trash2 } from 'lucide-react';

const COLORS = ['#22c55e', '#ef4444', '#f59e0b'];

interface Stats {
  total_processed: number;
  success: number;
  failed: number;
  skipped: number;
  success_rate: number;
  avg_processing_time_ms: number;
}

interface DailyStats {
  date: string;
  success: number;
  failed: number;
  skipped: number;
}

interface RecentLog {
  id: number;
  document_id: number;
  document_title: string | null;
  status: string;
  llm_provider: string | null;
  llm_model: string | null;
  error_message: string | null;
  processing_time_ms: number | null;
  processed_at: string;
}

export default function Dashboard() {
  const { t } = useTranslation();
  const [stats, setStats] = useState<Stats | null>(null);
  const [dailyStats, setDailyStats] = useState<DailyStats[]>([]);
  const [recentLogs, setRecentLogs] = useState<RecentLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [resetting, setResetting] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [statsRes, dailyRes, recentRes] = await Promise.all([
        statsApi.get(),
        statsApi.getDaily(7),
        statsApi.getRecent(10),
      ]);
      setStats(statsRes.data);
      setDailyStats(dailyRes.data);
      setRecentLogs(recentRes.data);
    } catch (error) {
      console.error('Failed to load stats:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async () => {
    if (!window.confirm(t('dashboard.confirmReset'))) {
      return;
    }
    setResetting(true);
    try {
      await statsApi.reset();
      loadData();
    } catch (error) {
      console.error('Failed to reset stats:', error);
      toast.error(t('dashboard.resetFailed'));
    } finally {
      setResetting(false);
    }
  };

  if (loading) {
    return <div className="text-gray-500">{t('common.loading')}</div>;
  }

  const pieData = stats ? [
    { name: t('dashboard.success'), value: stats.success },
    { name: t('dashboard.failed'), value: stats.failed },
    { name: t('dashboard.skipped'), value: stats.skipped },
  ] : [];

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">{t('dashboard.title')}</h1>
        <div className="flex gap-2">
          <button
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50"
          >
            <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
            {t('common.refresh')}
          </button>
          <button
            onClick={handleReset}
            disabled={resetting}
            className="flex items-center gap-2 px-3 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 disabled:opacity-50"
          >
            <Trash2 size={18} />
            {resetting ? t('dashboard.resetting') : t('dashboard.resetStats')}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-sm text-gray-500">{t('dashboard.totalProcessed')}</p>
          <p className="text-3xl font-bold text-gray-900">{stats?.total_processed || 0}</p>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-sm text-gray-500">{t('dashboard.successRate')}</p>
          <p className="text-3xl font-bold text-green-600">{stats?.success_rate || 0}%</p>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-sm text-gray-500">{t('dashboard.avgProcessingTime')}</p>
          <p className="text-3xl font-bold text-gray-900">{((stats?.avg_processing_time_ms || 0) / 1000).toFixed(1)}s</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-4">{t('dashboard.processingStatus')}</h2>
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
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex justify-center gap-4 mt-4">
            {pieData.map((entry, index) => (
              <div key={entry.name} className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS[index] }} />
                <span className="text-sm text-gray-600">{entry.name}: {entry.value}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-4">{t('dashboard.dailyProcessing')}</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={dailyStats}>
              <XAxis dataKey="date" tick={{ fontSize: 12 }} />
              <YAxis />
              <Tooltip />
              <Bar dataKey="success" fill="#22c55e" name={t('dashboard.success')} />
              <Bar dataKey="failed" fill="#ef4444" name={t('dashboard.failed')} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4">{t('dashboard.recentLogs')}</h2>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">{t('dashboard.colDocument')}</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">{t('dashboard.colStatus')}</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">{t('dashboard.colModel')}</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">{t('dashboard.colTime')}</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">{t('dashboard.colDate')}</th>
              </tr>
            </thead>
            <tbody>
              {recentLogs.map((log) => (
                <tr key={log.id} className="border-b hover:bg-gray-50">
                  <td className="py-3 px-4">{log.document_title || t('dashboard.docFallback', { id: log.document_id })}</td>
                  <td className="py-3 px-4">
                    <span className={`px-2 py-1 rounded text-xs font-medium ${
                      log.status === 'success' ? 'bg-green-100 text-green-800' :
                      log.status === 'failed' ? 'bg-red-100 text-red-800' :
                      'bg-yellow-100 text-yellow-800'
                    }`}>
                      {log.status}
                    </span>
                    {log.status === 'failed' && log.error_message && (
                      <p
                        className="mt-1 text-xs text-red-600 max-w-xs truncate"
                        title={log.error_message}
                      >
                        {log.error_message}
                      </p>
                    )}
                  </td>
                  <td className="py-3 px-4 text-sm text-gray-600">
                    {log.llm_model || '-'}
                  </td>
                  <td className="py-3 px-4 text-sm text-gray-600">
                    {log.processing_time_ms ? `${(log.processing_time_ms / 1000).toFixed(1)}s` : '-'}
                  </td>
                  <td className="py-3 px-4 text-sm text-gray-600">
                    {new Date(log.processed_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
