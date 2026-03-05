import { useEffect, useState } from 'react';
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
      alert(`Processed ${res.data.processed} documents`);
      loadDocuments();
      loadSchedulerStatus();
    } catch (err: any) {
      if (err.response?.status === 409) {
        alert(err.response?.data?.detail || 'Already processing');
      } else {
        alert(`Error: ${err.response?.data?.detail || err.message}`);
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
      alert(`Error: ${err.response?.data?.detail || err.message}`);
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
            <span className="font-medium text-blue-700">Processing in progress...</span>
            {schedulerStatus?.current_doc_id && (
              <span className="text-blue-600 text-sm ml-2">
                (Document #{schedulerStatus.current_doc_id})
              </span>
            )}
          </div>
        </div>
      )}

      {schedulerStatus?.running && !schedulerStatus.is_processing && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-3 flex items-center gap-2 text-sm text-green-700">
          <Clock size={16} />
          <span>Scheduler running - checks every {schedulerStatus.interval_minutes} min</span>
          {schedulerStatus.next_run && (
            <span className="text-green-600 ml-2">
              (next: {new Date(schedulerStatus.next_run).toLocaleTimeString()})
            </span>
          )}
        </div>
      )}

      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-lg font-semibold">Documents to Process</h2>
          <p className="text-sm text-gray-500">
            Documents tagged for AI processing
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={loadDocuments}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50"
          >
            <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
          <button
            onClick={handleProcessAll}
            disabled={isCurrentlyProcessing || documents.length === 0}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            <Play size={18} />
            Process All ({documents.length})
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
              Processing Result - Document #{result.document_id}
            </h3>
            <button
              onClick={() => setShowResult(false)}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              Hide
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
                {result.success ? 'Processing completed successfully' : 'Processing failed'}
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
                <h4 className="text-sm font-medium text-gray-700 mb-2">Updates Applied:</h4>
                <div className="text-sm text-gray-600 space-y-1">
                  {result.updates.title && <div>Title: {result.updates.title as string}</div>}
                  {result.updates.correspondent && <div>Correspondent ID: {String(result.updates.correspondent)}</div>}
                  {result.updates.document_type && <div>Document Type ID: {String(result.updates.document_type)}</div>}
                  {result.updates.tags && <div>Tags: {JSON.stringify(result.updates.tags as number[])}</div>}
                  {result.updates.custom_fields && <div>Custom Fields: {JSON.stringify(result.updates.custom_fields)}</div>}
                  {result.updates.content && <div>Content: {String(result.updates.content).substring(0, 100)}...</div>}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-center py-8 text-gray-500">Loading...</div>
      ) : documents.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          No documents to process
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Document</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">ID</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Created</th>
                <th className="text-right py-3 px-4 text-sm font-medium text-gray-500">Action</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id} className="border-t hover:bg-gray-50">
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <FileText size={18} className="text-gray-400" />
                      <span className="font-medium">
                        {doc.title || `Document #${doc.id}`}
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
                          Processing
                        </>
                      ) : (
                        <>
                          <Play size={14} />
                          Process
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
