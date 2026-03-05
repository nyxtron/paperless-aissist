import { useEffect, useState } from 'react';
import { configApi, documentsApi, schedulerApi } from '../api/client';
import { RefreshCw, CheckCircle, XCircle, Tag, Play, Square, Clock } from 'lucide-react';

interface Configs {
  paperless_url: string;
  paperless_token: string;
  process_tag: string;
  processed_tag: string;
  tag_blacklist: string;
  force_ocr_tag: string;
  force_ocr_fix_tag: string;
  ocr_post_process: string;
  llm_provider: string;
  llm_model: string;
  llm_api_base: string;
  llm_api_key: string;
  enable_vision: string;
  enable_fallback_ocr: string;
  llm_model_vision: string;
  llm_provider_vision: string;
  llm_api_base_vision: string;
  llm_api_key_vision: string;
}

interface PaperlessTag {
  id: number;
  name: string;
}

interface PaperlessItem {
  id: number;
  name: string;
}

export default function ConfigPanel() {
  const [configs, setConfigs] = useState<Configs>({
    paperless_url: '',
    paperless_token: '',
    process_tag: '',
    processed_tag: '',
    tag_blacklist: '',
    force_ocr_tag: 'force_ocr',
    force_ocr_fix_tag: 'force-ocr-fix',
    ocr_post_process: 'true',
    llm_provider: 'ollama',
    llm_model: 'qwen2.5:7b',
    llm_api_base: 'http://localhost:11434',
    llm_api_key: '',
    enable_vision: 'false',
    enable_fallback_ocr: 'false',
    llm_provider_vision: 'ollama',
    llm_model_vision: 'qwen2.5vl:7b',
    llm_api_base_vision: 'http://localhost:11434',
    llm_api_key_vision: '',
  });
  const [saving, setSaving] = useState(false);
  const [testingPaperless, setTestingPaperless] = useState(false);
  const [testingLlm, setTestingLlm] = useState(false);
  const [paperlessConnected, setPaperlessConnected] = useState(false);
  const [paperlessError, setPaperlessError] = useState<string | null>(null);
  const [availableTags, setAvailableTags] = useState<PaperlessTag[]>([]);
  const [availableCorrespondents, setAvailableCorrespondents] = useState<PaperlessItem[]>([]);
  const [llmResult, setLlmResult] = useState<{success: boolean; message: string} | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [schedulerStatus, setSchedulerStatus] = useState<{running: boolean; interval_minutes: number | null; next_run: string | null; is_processing: boolean; current_doc_id: number | null} | null>(null);
  const [schedulerInterval, setSchedulerInterval] = useState(5);
  const [schedulerLoading, setSchedulerLoading] = useState(false);

  useEffect(() => {
    loadConfigs();
    loadSchedulerStatus();
  }, []);

  const loadConfigs = async () => {
    try {
      const res = await configApi.getAll();
      const loadedConfigs = res.data;
      setConfigs((prev) => ({ ...prev, ...loadedConfigs }));
      
      if (loadedConfigs.paperless_url && loadedConfigs.paperless_token) {
        handleTestPaperless();
      }
    } catch (error) {
      console.error('Failed to load configs:', error);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      for (const [key, value] of Object.entries(configs)) {
        await configApi.set(key, value);
      }
      alert('Configuration saved!');
    } catch (error) {
      console.error('Failed to save configs:', error);
      alert('Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  const handleTestPaperless = async () => {
    setTestingPaperless(true);
    setPaperlessError(null);
    setPaperlessConnected(false);
    try {
      const res = await documentsApi.getTags();
      setAvailableTags(res.data.tags || []);
      setAvailableCorrespondents(res.data.correspondents || []);
      setPaperlessConnected(true);
    } catch (error: any) {
      setPaperlessError(error.response?.data?.detail || error.message);
    } finally {
      setTestingPaperless(false);
    }
  };

  const handleTestLlm = async () => {
    setTestingLlm(true);
    setLlmResult(null);
    try {
      console.log('[LLM Test] Calling backend to test Ollama connection...');
      const res = await fetch('/api/config/test-ollama', {
        method: 'POST',
      });
      const data = await res.json();
      console.log('[LLM Test] Response:', data);
      
      // Build message from main and vision results
      let message = '';
      
      if (data.main) {
        message += `Main: ${data.main.message}`;
      }
      
      if (data.vision !== null && data.vision !== undefined) {
        message += `\nVision: ${data.vision.message}`;
      }
      
      setLlmResult({ success: data.success, message: message });
    } catch (error: any) {
      console.error('[LLM Test] Error:', error);
      setLlmResult({ success: false, message: `Error: ${error.message}` });
    } finally {
      setTestingLlm(false);
    }
  };

  const handleTrigger = async () => {
    setTriggering(true);
    try {
      const res = await documentsApi.trigger();
      alert(`Processed ${res.data.processed} documents`);
    } catch (error: any) {
      alert(`Error: ${error.response?.data?.detail || error.message}`);
    } finally {
      setTriggering(false);
    }
  };

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
      alert('Failed to start scheduler');
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
      alert('Failed to stop scheduler');
    } finally {
      setSchedulerLoading(false);
    }
  };

  const handleClearState = async () => {
    if (!window.confirm('Clear stuck processing state? Only do this if processing was interrupted.')) {
      return;
    }
    try {
      await schedulerApi.clearState();
      await loadSchedulerStatus();
      alert('Processing state cleared');
    } catch (error) {
      console.error('Failed to clear state:', error);
      alert('Failed to clear state');
    }
  };

  const field = 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500';
  const label = 'block text-sm font-medium text-gray-700 mb-1';
  const hint = 'text-xs text-gray-500 mt-1';

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">Configuration</h1>
        <div className="flex gap-2">
          <button
            onClick={handleTestPaperless}
            disabled={testingPaperless}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50"
          >
            {testingPaperless ? <RefreshCw size={18} className="animate-spin" /> : <CheckCircle size={18} />}
            Check / Load Tags
          </button>
          <button
            onClick={handleTrigger}
            disabled={triggering}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {triggering ? 'Processing...' : 'Process Documents'}
          </button>
        </div>
      </div>

      {paperlessError && (
        <div className="p-4 rounded-lg flex items-center gap-2 bg-red-50 text-red-700">
          <XCircle size={20} />
          {paperlessError}
        </div>
      )}

      {paperlessConnected && (
        <div className="p-4 rounded-lg flex items-center gap-2 bg-green-50 text-green-700">
          <CheckCircle size={20} />
          Connected! Loaded {availableTags.length} tags, {availableCorrespondents.length} correspondents
        </div>
      )}

      {/* Paperless Settings */}
      <div className="bg-white rounded-lg shadow p-6 space-y-6">
        <h2 className="text-lg font-semibold border-b pb-2">Paperless-ngx Settings</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={label}>Paperless URL</label>
            <input
              type="text"
              value={configs.paperless_url}
              onChange={(e) => setConfigs({ ...configs, paperless_url: e.target.value })}
              placeholder="http://localhost:8000"
              className={field}
            />
          </div>
          <div>
            <label className={label}>API Token</label>
            <input
              type="password"
              value={configs.paperless_token}
              onChange={(e) => setConfigs({ ...configs, paperless_token: e.target.value })}
              placeholder="Enter your Paperless API token"
              className={field}
            />
          </div>
        </div>

        {availableTags.length > 0 && (
          <div className="flex items-center gap-2 text-sm text-gray-500 border-t pt-4 -mb-2">
            <Tag size={14} />
            Tag dropdowns populated from Paperless
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className={label}>Process Tag</label>
            <select value={configs.process_tag} onChange={(e) => setConfigs({ ...configs, process_tag: e.target.value })} className={field}>
              <option value="">-- Select tag --</option>
              {availableTags.map((tag) => <option key={tag.id} value={tag.name}>{tag.name}</option>)}
            </select>
            <p className={hint}>Documents with this tag will be processed</p>
          </div>
          <div>
            <label className={label}>Processed Tag</label>
            <select value={configs.processed_tag} onChange={(e) => setConfigs({ ...configs, processed_tag: e.target.value })} className={field}>
              <option value="">-- Select tag --</option>
              {availableTags.map((tag) => <option key={tag.id} value={tag.name}>{tag.name}</option>)}
            </select>
            <p className={hint}>Added after successful processing</p>
          </div>
          <div>
            <label className={label}>OCR Post-Processing</label>
            <select value={configs.ocr_post_process} onChange={(e) => setConfigs({ ...configs, ocr_post_process: e.target.value })} className={field}>
              <option value="false">Disabled</option>
              <option value="true">Enabled</option>
            </select>
            <p className={hint}>Fix OCR errors with LLM after extraction</p>
          </div>
          <div className="md:col-span-3">
            <label className={label}>Tag Blacklist</label>
            <input
              type="text"
              value={configs.tag_blacklist}
              onChange={(e) => setConfigs({ ...configs, tag_blacklist: e.target.value })}
              placeholder="e.g. inbox, todo, review"
              className={field}
            />
            <p className={hint}>Comma-separated tag names the LLM must not assign</p>
          </div>
          <div>
            <label className={label}>Force OCR Tag</label>
            <select value={configs.force_ocr_tag} onChange={(e) => setConfigs({ ...configs, force_ocr_tag: e.target.value })} className={field}>
              <option value="">-- None --</option>
              {availableTags.map((tag) => <option key={tag.id} value={tag.name}>{tag.name}</option>)}
            </select>
            <p className={hint}>Tag to force vision OCR on a document</p>
          </div>
          <div>
            <label className={label}>Force OCR Fix Tag</label>
            <select value={configs.force_ocr_fix_tag} onChange={(e) => setConfigs({ ...configs, force_ocr_fix_tag: e.target.value })} className={field}>
              <option value="">-- None --</option>
              {availableTags.map((tag) => <option key={tag.id} value={tag.name}>{tag.name}</option>)}
            </select>
            <p className={hint}>Tag to force OCR + LLM fix on a document</p>
          </div>
        </div>
      </div>

      {/* LLM Settings */}
      <div className="bg-white rounded-lg shadow p-6 space-y-6">
        <div className="flex justify-between items-center border-b pb-2">
          <h2 className="text-lg font-semibold">LLM Settings</h2>
          <button
            onClick={handleTestLlm}
            disabled={testingLlm}
            className="flex items-center gap-2 px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 disabled:opacity-50"
          >
            {testingLlm ? <RefreshCw size={14} className="animate-spin" /> : <CheckCircle size={14} />}
            Test Connection
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={label}>Provider</label>
            <select value={configs.llm_provider} onChange={(e) => setConfigs({ ...configs, llm_provider: e.target.value })} className={field}>
              <option value="ollama">Ollama</option>
              <option value="openai">OpenAI</option>
              <option value="grok">Grok (xAI)</option>
            </select>
          </div>
          <div>
            <label className={label}>Model</label>
            <input
              type="text"
              value={configs.llm_model}
              onChange={(e) => setConfigs({ ...configs, llm_model: e.target.value })}
              placeholder={configs.llm_provider === 'openai' ? 'gpt-4o-mini' : configs.llm_provider === 'grok' ? 'grok-3-mini' : 'qwen2.5:7b'}
              className={field}
            />
          </div>
          <div>
            <label className={label}>API Base URL</label>
            <input
              type="text"
              value={configs.llm_api_base}
              onChange={(e) => setConfigs({ ...configs, llm_api_base: e.target.value })}
              placeholder={configs.llm_provider === 'openai' ? 'https://api.openai.com/v1' : configs.llm_provider === 'grok' ? 'https://api.x.ai/v1' : 'http://localhost:11434'}
              className={field}
            />
          </div>
          <div>
            <label className={label}>API Key <span className="font-normal text-gray-400">(optional)</span></label>
            <input
              type="password"
              value={configs.llm_api_key}
              onChange={(e) => setConfigs({ ...configs, llm_api_key: e.target.value })}
              placeholder={configs.llm_provider === 'ollama' ? 'Leave empty for local Ollama' : 'xai-... / sk-...'}
              className={field}
            />
            <p className={hint}>Required for OpenAI; also used for hosted/proxied Ollama</p>
          </div>
          <div>
            <label className={label}>Vision / OCR</label>
            <select value={configs.enable_vision} onChange={(e) => setConfigs({ ...configs, enable_vision: e.target.value })} className={field}>
              <option value="false">Disabled</option>
              <option value="true">Enabled</option>
            </select>
            <p className={hint}>Use a vision model to OCR document images</p>
          </div>
          <div>
            <label className={label}>Fallback OCR (Tesseract)</label>
            <select value={configs.enable_fallback_ocr} onChange={(e) => setConfigs({ ...configs, enable_fallback_ocr: e.target.value })} className={field}>
              <option value="false">Disabled</option>
              <option value="true">Enabled</option>
            </select>
            <p className={hint}>Use local Tesseract OCR if vision model fails</p>
          </div>
        </div>

        {configs.enable_vision === 'true' && (
          <div className="pt-4 border-t">
            <h3 className="text-sm font-semibold text-gray-700 mb-4">Vision Model Settings</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className={label}>Provider</label>
                <select value={configs.llm_provider_vision} onChange={(e) => setConfigs({ ...configs, llm_provider_vision: e.target.value })} className={field}>
                  <option value="ollama">Ollama</option>
                  <option value="openai">OpenAI</option>
                  <option value="grok">Grok (xAI)</option>
                </select>
              </div>
              <div>
                <label className={label}>Vision Model</label>
                <input
                  type="text"
                  value={configs.llm_model_vision}
                  onChange={(e) => setConfigs({ ...configs, llm_model_vision: e.target.value })}
                  placeholder={configs.llm_provider_vision === 'openai' ? 'gpt-4o' : configs.llm_provider_vision === 'grok' ? 'grok-2-vision-1212' : 'qwen2.5vl:7b'}
                  className={field}
                />
              </div>
              <div>
                <label className={label}>API Base URL</label>
                <input
                  type="text"
                  value={configs.llm_api_base_vision}
                  onChange={(e) => setConfigs({ ...configs, llm_api_base_vision: e.target.value })}
                  placeholder={configs.llm_provider_vision === 'openai' ? 'https://api.openai.com/v1' : configs.llm_provider_vision === 'grok' ? 'https://api.x.ai/v1' : 'http://localhost:11434'}
                  className={field}
                />
              </div>
              <div>
                <label className={label}>API Key <span className="font-normal text-gray-400">(optional)</span></label>
                <input
                  type="password"
                  value={configs.llm_api_key_vision}
                  onChange={(e) => setConfigs({ ...configs, llm_api_key_vision: e.target.value })}
                  placeholder={configs.llm_provider_vision === 'ollama' ? 'Leave empty for local Ollama' : 'xai-... / sk-...'}
                  className={field}
                />
                <p className={hint}>Required for OpenAI; also used for hosted/proxied Ollama</p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Scheduler */}
      <div className="bg-white rounded-lg shadow p-6 space-y-6">
        <div className="flex items-center justify-between border-b pb-2">
          <div className="flex items-center gap-2">
            <Clock size={20} className="text-gray-700" />
            <h2 className="text-lg font-semibold">Auto-Processing Scheduler</h2>
            {schedulerStatus?.running ? (
              <span className="flex items-center gap-1 px-2 py-1 bg-green-100 text-green-700 text-sm rounded">
                <CheckCircle size={12} /> Running
              </span>
            ) : (
              <span className="flex items-center gap-1 px-2 py-1 bg-gray-100 text-gray-600 text-sm rounded">
                <XCircle size={12} /> Stopped
              </span>
            )}
            {schedulerStatus?.is_processing && (
              <span className="flex items-center gap-1 px-2 py-1 bg-blue-100 text-blue-700 text-sm rounded">
                <RefreshCw size={12} className="animate-spin" /> Processing...
              </span>
            )}
          </div>
        </div>

        <div className="flex items-end gap-4">
          <div>
            <label className={label}>Check interval (minutes)</label>
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
                <Square size={18} />
                Stop
              </button>
            ) : (
              <button
                onClick={handleSchedulerStart}
                disabled={schedulerLoading}
                className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
              >
                <Play size={18} />
                Start
              </button>
            )}
          </div>
          {schedulerStatus?.running && schedulerStatus.next_run && (
            <span className="text-sm text-gray-500">
              Next run: {new Date(schedulerStatus.next_run).toLocaleString()}
            </span>
          )}
        </div>

        {schedulerStatus?.is_processing && schedulerStatus.current_doc_id && (
          <div className="text-sm text-blue-600">
            Currently processing document #{schedulerStatus.current_doc_id}
          </div>
        )}

        <div className="border-t pt-4">
          <button onClick={handleClearState} className="text-sm text-gray-500 hover:text-gray-700 underline">
            Clear stuck processing state
          </button>
        </div>
      </div>

      {llmResult && (
        <div className={`p-4 rounded-lg flex items-center gap-2 ${llmResult.success ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
          {llmResult.success ? <CheckCircle size={20} /> : <XCircle size={20} />}
          <span className="whitespace-pre-line">{llmResult.message}</span>
        </div>
      )}

      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Save Configuration'}
        </button>
      </div>
    </div>
  );
}
