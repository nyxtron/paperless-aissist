import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { schedulerApi } from '../api/client';
import { Clock, Play, Square, RefreshCw, CheckCircle, XCircle } from 'lucide-react';

interface SchedulerStatus {
  running: boolean;
  interval_minutes: number | null;
  next_run: string | null;
  is_processing: boolean;
  current_doc_id: number | null;
}

interface ConfigSectionProps {
  config: Record<string, string>;
  onSave: (key: string, value: string) => Promise<void>;
  onTest?: (key: string) => Promise<boolean>;
}

export function ConfigSectionScheduler(_props: ConfigSectionProps) {
  const { t } = useTranslation();
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus | null>(null);
  const [schedulerInterval, setSchedulerInterval] = useState(5);
  const [schedulerLoading, setSchedulerLoading] = useState(false);

  const label = 'block text-sm font-medium text-gray-700 mb-1';

  useEffect(() => {
    loadSchedulerStatus();
  }, []);

  const loadSchedulerStatus = async () => {
    try {
      const res = await schedulerApi.getStatus();
      setSchedulerStatus(res.data);
      if (res.data.interval_minutes) {
        setSchedulerInterval(res.data.interval_minutes);
      }
    } catch (error) {
      console.error('Failed to load scheduler status:', error);
    }
  };

  const handleSchedulerStart = async () => {
    setSchedulerLoading(true);
    try {
      await schedulerApi.start(schedulerInterval);
      await loadSchedulerStatus();
    } catch (error) {
      console.error('Failed to start scheduler:', error);
      toast.error(t('config.schedulerStartFailed'));
    } finally {
      setSchedulerLoading(false);
    }
  };

  const handleSchedulerStop = async () => {
    setSchedulerLoading(true);
    try {
      await schedulerApi.stop();
      await loadSchedulerStatus();
    } catch (error) {
      console.error('Failed to stop scheduler:', error);
      toast.error(t('config.schedulerStopFailed'));
    } finally {
      setSchedulerLoading(false);
    }
  };

  const handleClearState = async () => {
    if (!window.confirm(t('config.clearStateConfirm'))) return;
    try {
      await schedulerApi.clearState();
      await loadSchedulerStatus();
      toast.success(t('config.clearStateSuccess'));
    } catch (error) {
      console.error('Failed to clear state:', error);
      toast.error(t('config.clearStateFailed'));
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-6 space-y-6">
      <div className="flex items-center justify-between border-b pb-3 mb-4">
        <div className="flex items-center gap-2">
          <Clock size={18} className="text-blue-600" />
          <h2 className="text-lg font-semibold text-gray-800">{t('config.schedulerSection')}</h2>
          {schedulerStatus?.running ? (
            <span className="flex items-center gap-1 px-2 py-1 bg-green-100 text-green-700 text-xs rounded-full">
              <CheckCircle size={11} /> {t('config.schedulerRunning')}
            </span>
          ) : (
            <span className="flex items-center gap-1 px-2 py-1 bg-gray-100 text-gray-500 text-xs rounded-full">
              <XCircle size={11} /> {t('config.schedulerStopped')}
            </span>
          )}
          {schedulerStatus?.is_processing && (
            <span className="flex items-center gap-1 px-2 py-1 bg-blue-100 text-blue-700 text-xs rounded-full">
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
            className="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
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
          <span className="text-sm text-gray-500">
            {t('config.schedulerNextRun', { time: new Date(schedulerStatus.next_run).toLocaleString() })}
          </span>
        )}
      </div>

      {schedulerStatus?.is_processing && schedulerStatus.current_doc_id && (
        <div className="text-sm text-blue-600">
          {t('config.schedulerCurrentDoc', { id: schedulerStatus.current_doc_id })}
        </div>
      )}

      <div className="border-t pt-4">
        <button
          onClick={handleClearState}
          className="text-sm text-gray-500 hover:text-gray-700 underline"
        >
          {t('config.clearStuckState')}
        </button>
      </div>
    </div>
  );
}
