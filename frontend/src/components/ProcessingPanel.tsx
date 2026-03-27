import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { documentsApi, schedulerApi } from '../api/client';
import { Play, RefreshCw, FileText, CheckCircle, XCircle, Clock } from 'lucide-react';

interface TaggedDocument {
  id: number;
  title: string | null;
  created: string;
  added: string;
  tags: number[];
}

interface ProcessingStep {
  name: string;
  status: string;
  duration_ms: number;
  error?: string;
}

interface ProcessingResult {
  success: boolean;
  document_id: number;
  title: string;
  updates: {
    title?: string;
    correspondent?: number;
    document_type?: number;
    tags?: number[];
    custom_fields?: Array<{field: number; value: string}>;
    content?: string;
    [key: string]: unknown;
  };
  processing_time_ms: number;
  steps: ProcessingStep[];
  error?: string;
}

interface SchedulerStatus {
  running: boolean;
  interval_minutes: number | null;
  next_run: string | null;
  is_processing: boolean;
  current_doc_id: number | null;
}

export default function ProcessingPanel() {
  const { t } = useTranslation();
  const [documents, setDocuments] = useState<TaggedDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [processingId, setProcessingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ProcessingResult | null>(null);
  const [showResult, setShowResult] = useState(false);
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus | null>(null);

  useEffect(() => {
    loadDocuments();
    loadSchedulerStatus();

    const interval = setInterval(loadSchedulerStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  const loadDocuments = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await documentsApi.getTagged();
      setDocuments(res.data.documents || []);
      if (res.data.error) {
        setError(res.data.error);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
      setDocuments([]);
    } finally {
      setLoading(false);
    }
  };

  const loadSchedulerStatus = async () => {
    try {
      const res = await schedulerApi.getStatus();
      setSchedulerStatus(res.data);
    } catch (error) {
      console.error('Failed to load scheduler status:', error);
    }
  };

  const handleProcessAll = async () => {
    setProcessing(true);
    try {
      const res = await documentsApi.trigger();
      toast.success(t('processing.processedCount', { count: res.data.processed }));
      loadDocuments();
      loadSchedulerStatus();
    } catch (err: any) {
      if (err.response?.status === 409) {
        toast.error(err.response?.data?.detail || t('processing.alreadyProcessing'));
      } else {
        toast.error(`Error: ${err.response?.data?.detail || err.message}`);
      }
    } finally {
      setProcessing(false);
    }
  };

  const handleProcessOne = async (docId: number) => {
    setProcessingId(docId);
    setShowResult(false);
    setResult(null);
    try {
      const res = await documentsApi.process(docId);
      setResult(res.data);
      setShowResult(true);
      loadDocuments();
      loadSchedulerStatus();
    } catch (err: any) {
      toast.error(`Error: ${err.response?.data?.detail || err.message}`);
    } finally {
      setProcessingId(null);
    }
  };

  const formatDuration = (ms: number): string => {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}m`;
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle size={14} className="text-green-500" />;
      case 'failed':
        return <XCircle size={14} className="text-red-500" />;
      default:
        return <Clock size={14} className="text-yellow-500" />;
    }
  };

  const isCurrentlyProcessing = schedulerStatus?.is_processing || processing;

  return (
    <div className="space-y-6">
      {isCurrentlyProcessing && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-center gap-3">
          <RefreshCw size={20} className="animate-spin text-blue-600" />
          <div>
            <span className="font-medium text-blue-700">{t('processing.processingInProgress')}</span>
            {schedulerStatus?.current_doc_id && (
              <span className="text-blue-600 text-sm ml-2">
                {t('processing.currentDoc', { id: schedulerStatus.current_doc_id })}
              </span>
            )}
          </div>
        </div>
      )}

      {schedulerStatus?.running && !schedulerStatus.is_processing && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-3 flex items-center gap-2 text-sm text-green-700">
          <Clock size={16} />
          <span>{t('processing.schedulerRunning', { minutes: schedulerStatus.interval_minutes })}</span>
          {schedulerStatus.next_run && (
            <span className="text-green-600 ml-2">
              {t('processing.schedulerNext', { time: new Date(schedulerStatus.next_run).toLocaleTimeString() })}
            </span>
          )}
        </div>
      )}

      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-lg font-semibold">{t('processing.sectionTitle')}</h2>
          <p className="text-sm text-gray-500">
            {t('processing.sectionSubtitle')}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={loadDocuments}
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

      {error && (
        <div className="p-4 bg-yellow-50 text-yellow-700 rounded-lg">
          {error}
        </div>
      )}

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

            <div className="space-y-2">
              {result.steps.map((step, index) => (
                <div
                  key={index}
                  className={`flex items-center justify-between px-3 py-2 rounded ${
                    step.status === 'completed' ? 'bg-green-50' :
                    step.status === 'failed' ? 'bg-red-50' : 'bg-yellow-50'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {getStatusIcon(step.status)}
                    <span className="text-sm text-gray-700">{step.name}</span>
                    {step.error && (
                      <span className="text-xs text-red-600 ml-2">- {step.error}</span>
                    )}
                  </div>
                  <span className="text-xs text-gray-500">
                    {formatDuration(step.duration_ms)}
                  </span>
                </div>
              ))}
            </div>

            {result.updates && Object.keys(result.updates).length > 0 && (
              <div className="mt-4 pt-4 border-t">
                <h4 className="text-sm font-medium text-gray-700 mb-2">{t('processing.updatesApplied')}</h4>
                <div className="text-sm text-gray-600 space-y-1">
                  {result.updates.title && <div>{t('processing.updateTitle')} {result.updates.title as string}</div>}
                  {result.updates.correspondent && <div>{t('processing.updateCorrespondent')} {String(result.updates.correspondent)}</div>}
                  {result.updates.document_type && <div>{t('processing.updateDocType')} {String(result.updates.document_type)}</div>}
                  {result.updates.tags && <div>{t('processing.updateTags')} {JSON.stringify(result.updates.tags as number[])}</div>}
                  {result.updates.custom_fields && <div>{t('processing.updateCustomFields')} {JSON.stringify(result.updates.custom_fields)}</div>}
                  {result.updates.content && <div>{t('processing.updateContent')} {String(result.updates.content).substring(0, 100)}...</div>}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-center py-8 text-gray-500">{t('common.loading')}</div>
      ) : documents.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          {t('processing.noDocuments')}
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">{t('processing.colDocument')}</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">{t('processing.colId')}</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">{t('processing.colCreated')}</th>
                <th className="text-right py-3 px-4 text-sm font-medium text-gray-500">{t('processing.colAction')}</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id} className="border-t hover:bg-gray-50">
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <FileText size={18} className="text-gray-400" />
                      <span className="font-medium">
                        {doc.title || t('processing.docFallback', { id: doc.id })}
                      </span>
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
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
