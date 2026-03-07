import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
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
  llm_timeout: string;
  llm_timeout_vision: string;
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
  const { t } = useTranslation();
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
    llm_timeout: '600',
    llm_timeout_vision: '600',
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
      alert(t('config.savedSuccess'));
    } catch (error) {
      console.error('Failed to save configs:', error);
      alert(t('config.saveFailed'));
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
      alert(t('config.processedCount', { count: res.data.processed }));
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
      alert(t('config.schedulerStartFailed'));
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
      alert(t('config.schedulerStopFailed'));
    } finally {
      setSchedulerLoading(false);
    }
  };

  const handleClearState = async () => {
    if (!window.confirm(t('config.clearStateConfirm'))) {
      return;
    }
    try {
      await schedulerApi.clearState();
      await loadSchedulerStatus();
      alert(t('config.clearStateSuccess'));
    } catch (error) {
      console.error('Failed to clear state:', error);
      alert(t('config.clearStateFailed'));
    }
  };

  const field = 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500';
  const label = 'block text-sm font-medium text-gray-700 mb-1';
  const hint = 'text-xs text-gray-500 mt-1';

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">{t('config.title')}</h1>
        <div className="flex gap-2">
          <button
            onClick={handleTestPaperless}
            disabled={testingPaperless}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50"
          >
            {testingPaperless ? <RefreshCw size={18} className="animate-spin" /> : <CheckCircle size={18} />}
            {t('config.checkLoadTags')}
          </button>
          <button
            onClick={handleTrigger}
            disabled={triggering}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {triggering ? t('config.processing') : t('config.processDocuments')}
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
          {t('config.connectedMsg', { tags: availableTags.length, correspondents: availableCorrespondents.length })}
        </div>
      )}

      {/* Paperless Settings */}
      <div className="bg-white rounded-lg shadow p-6 space-y-6">
        <h2 className="text-lg font-semibold border-b pb-2">{t('config.paperlessSection')}</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={label}>{t('config.paperlessUrl')}</label>
            <input
              type="text"
              value={configs.paperless_url}
              onChange={(e) => setConfigs({ ...configs, paperless_url: e.target.value })}
              placeholder="http://localhost:8000"
              className={field}
            />
          </div>
          <div>
            <label className={label}>{t('config.apiToken')}</label>
            <input
              type="password"
              value={configs.paperless_token}
              onChange={(e) => setConfigs({ ...configs, paperless_token: e.target.value })}
              placeholder={t('config.apiTokenPlaceholder')}
              className={field}
            />
          </div>
        </div>

        {availableTags.length > 0 && (
          <div className="flex items-center gap-2 text-sm text-gray-500 border-t pt-4 -mb-2">
            <Tag size={14} />
            {t('config.tagDropdownHint')}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className={label}>{t('config.processTag')}</label>
            <select value={configs.process_tag} onChange={(e) => setConfigs({ ...configs, process_tag: e.target.value })} className={field}>
              <option value="">{t('common.selectTag')}</option>
              {availableTags.map((tag) => <option key={tag.id} value={tag.name}>{tag.name}</option>)}
            </select>
            <p className={hint}>{t('config.processTagHint')}</p>
          </div>
          <div>
            <label className={label}>{t('config.processedTag')}</label>
            <select value={configs.processed_tag} onChange={(e) => setConfigs({ ...configs, processed_tag: e.target.value })} className={field}>
              <option value="">{t('common.selectTag')}</option>
              {availableTags.map((tag) => <option key={tag.id} value={tag.name}>{tag.name}</option>)}
            </select>
            <p className={hint}>{t('config.processedTagHint')}</p>
          </div>
          <div>
            <label className={label}>{t('config.ocrPostProcess')}</label>
            <select value={configs.ocr_post_process} onChange={(e) => setConfigs({ ...configs, ocr_post_process: e.target.value })} className={field}>
              <option value="false">{t('common.disabled')}</option>
              <option value="true">{t('common.enabled')}</option>
            </select>
            <p className={hint}>{t('config.ocrPostProcessHint')}</p>
          </div>
          <div className="md:col-span-3">
            <label className={label}>{t('config.tagBlacklist')}</label>
            <input
              type="text"
              value={configs.tag_blacklist}
              onChange={(e) => setConfigs({ ...configs, tag_blacklist: e.target.value })}
              placeholder={t('config.tagBlacklistPlaceholder')}
              className={field}
            />
            <p className={hint}>{t('config.tagBlacklistHint')}</p>
          </div>
          <div>
            <label className={label}>{t('config.forceOcrTag')}</label>
            <select value={configs.force_ocr_tag} onChange={(e) => setConfigs({ ...configs, force_ocr_tag: e.target.value })} className={field}>
              <option value="">{t('common.none')}</option>
              {availableTags.map((tag) => <option key={tag.id} value={tag.name}>{tag.name}</option>)}
            </select>
            <p className={hint}>{t('config.forceOcrTagHint')}</p>
          </div>
          <div>
            <label className={label}>{t('config.forceOcrFixTag')}</label>
            <select value={configs.force_ocr_fix_tag} onChange={(e) => setConfigs({ ...configs, force_ocr_fix_tag: e.target.value })} className={field}>
              <option value="">{t('common.none')}</option>
              {availableTags.map((tag) => <option key={tag.id} value={tag.name}>{tag.name}</option>)}
            </select>
            <p className={hint}>{t('config.forceOcrFixTagHint')}</p>
          </div>
        </div>
      </div>

      {/* LLM Settings */}
      <div className="bg-white rounded-lg shadow p-6 space-y-6">
        <div className="flex justify-between items-center border-b pb-2">
          <h2 className="text-lg font-semibold">{t('config.llmSection')}</h2>
          <button
            onClick={handleTestLlm}
            disabled={testingLlm}
            className="flex items-center gap-2 px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 disabled:opacity-50"
          >
            {testingLlm ? <RefreshCw size={14} className="animate-spin" /> : <CheckCircle size={14} />}
            {t('config.testConnection')}
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={label}>{t('config.provider')}</label>
            <select value={configs.llm_provider} onChange={(e) => setConfigs({ ...configs, llm_provider: e.target.value })} className={field}>
              <option value="ollama">Ollama</option>
              <option value="openai">OpenAI</option>
              <option value="grok">Grok (xAI)</option>
            </select>
          </div>
          <div>
            <label className={label}>{t('config.model')}</label>
            <input
              type="text"
              value={configs.llm_model}
              onChange={(e) => setConfigs({ ...configs, llm_model: e.target.value })}
              placeholder={configs.llm_provider === 'openai' ? 'gpt-4o-mini' : configs.llm_provider === 'grok' ? 'grok-3-mini' : 'qwen2.5:7b'}
              className={field}
            />
          </div>
          <div>
            <label className={label}>{t('config.apiBaseUrl')}</label>
            <input
              type="text"
              value={configs.llm_api_base}
              onChange={(e) => setConfigs({ ...configs, llm_api_base: e.target.value })}
              placeholder={configs.llm_provider === 'openai' ? 'https://api.openai.com/v1' : configs.llm_provider === 'grok' ? 'https://api.x.ai/v1' : 'http://localhost:11434'}
              className={field}
            />
          </div>
          <div>
            <label className={label}>{t('config.apiKey')} <span className="font-normal text-gray-400">({t('common.optional')})</span></label>
            <input
              type="password"
              value={configs.llm_api_key}
              onChange={(e) => setConfigs({ ...configs, llm_api_key: e.target.value })}
              placeholder={configs.llm_provider === 'ollama' ? t('config.apiKeyPlaceholderOllama') : t('config.apiKeyPlaceholderCloud')}
              className={field}
            />
            <p className={hint}>{t('config.apiKeyHint')}</p>
          </div>
          <div>
            <label className={label}>{t('config.visionOcr')}</label>
            <select value={configs.enable_vision} onChange={(e) => setConfigs({ ...configs, enable_vision: e.target.value })} className={field}>
              <option value="false">{t('common.disabled')}</option>
              <option value="true">{t('common.enabled')}</option>
            </select>
            <p className={hint}>{t('config.visionOcrHint')}</p>
          </div>
          <div>
            <label className={label}>{t('config.fallbackOcr')}</label>
            <select value={configs.enable_fallback_ocr} onChange={(e) => setConfigs({ ...configs, enable_fallback_ocr: e.target.value })} className={field}>
              <option value="false">{t('common.disabled')}</option>
              <option value="true">{t('common.enabled')}</option>
            </select>
            <p className={hint}>{t('config.fallbackOcrHint')}</p>
          </div>
          <div>
            <label className={label}>{t('config.llmTimeout')}</label>
            <input
              type="number"
              min="30"
              max="3600"
              value={configs.llm_timeout}
              onChange={(e) => setConfigs({ ...configs, llm_timeout: e.target.value })}
              className="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            />
            <p className={hint}>{t('config.llmTimeoutHint')}</p>
          </div>
        </div>

        {configs.enable_vision === 'true' && (
          <div className="pt-4 border-t">
            <h3 className="text-sm font-semibold text-gray-700 mb-4">{t('config.visionModelSection')}</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className={label}>{t('config.provider')}</label>
                <select value={configs.llm_provider_vision} onChange={(e) => setConfigs({ ...configs, llm_provider_vision: e.target.value })} className={field}>
                  <option value="ollama">Ollama</option>
                  <option value="openai">OpenAI</option>
                  <option value="grok">Grok (xAI)</option>
                </select>
              </div>
              <div>
                <label className={label}>{t('config.visionModel')}</label>
                <input
                  type="text"
                  value={configs.llm_model_vision}
                  onChange={(e) => setConfigs({ ...configs, llm_model_vision: e.target.value })}
                  placeholder={configs.llm_provider_vision === 'openai' ? 'gpt-4o' : configs.llm_provider_vision === 'grok' ? 'grok-2-vision-1212' : 'qwen2.5vl:7b'}
                  className={field}
                />
              </div>
              <div>
                <label className={label}>{t('config.apiBaseUrl')}</label>
                <input
                  type="text"
                  value={configs.llm_api_base_vision}
                  onChange={(e) => setConfigs({ ...configs, llm_api_base_vision: e.target.value })}
                  placeholder={configs.llm_provider_vision === 'openai' ? 'https://api.openai.com/v1' : configs.llm_provider_vision === 'grok' ? 'https://api.x.ai/v1' : 'http://localhost:11434'}
                  className={field}
                />
              </div>
              <div>
                <label className={label}>{t('config.apiKey')} <span className="font-normal text-gray-400">({t('common.optional')})</span></label>
                <input
                  type="password"
                  value={configs.llm_api_key_vision}
                  onChange={(e) => setConfigs({ ...configs, llm_api_key_vision: e.target.value })}
                  placeholder={configs.llm_provider_vision === 'ollama' ? t('config.apiKeyPlaceholderOllama') : t('config.apiKeyPlaceholderCloud')}
                  className={field}
                />
                <p className={hint}>{t('config.apiKeyHint')}</p>
              </div>
              <div>
                <label className={label}>{t('config.llmTimeoutVision')}</label>
                <input
                  type="number"
                  min="30"
                  max="3600"
                  value={configs.llm_timeout_vision}
                  onChange={(e) => setConfigs({ ...configs, llm_timeout_vision: e.target.value })}
                  className="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
                <p className={hint}>{t('config.llmTimeoutVisionHint')}</p>
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
            <h2 className="text-lg font-semibold">{t('config.schedulerSection')}</h2>
            {schedulerStatus?.running ? (
              <span className="flex items-center gap-1 px-2 py-1 bg-green-100 text-green-700 text-sm rounded">
                <CheckCircle size={12} /> {t('config.schedulerRunning')}
              </span>
            ) : (
              <span className="flex items-center gap-1 px-2 py-1 bg-gray-100 text-gray-600 text-sm rounded">
                <XCircle size={12} /> {t('config.schedulerStopped')}
              </span>
            )}
            {schedulerStatus?.is_processing && (
              <span className="flex items-center gap-1 px-2 py-1 bg-blue-100 text-blue-700 text-sm rounded">
                <RefreshCw size={12} className="animate-spin" /> {t('config.schedulerProcessing')}
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
                <Square size={18} />
                {t('config.stop')}
              </button>
            ) : (
              <button
                onClick={handleSchedulerStart}
                disabled={schedulerLoading}
                className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
              >
                <Play size={18} />
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
          <button onClick={handleClearState} className="text-sm text-gray-500 hover:text-gray-700 underline">
            {t('config.clearStuckState')}
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
          {saving ? t('config.saving') : t('config.saveConfiguration')}
        </button>
      </div>
    </div>
  );
}
