import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { configApi } from '../api/client';
import { ConfigSectionPaperless } from './ConfigSectionPaperless';
import { ConfigSectionLLM } from './ConfigSectionLLM';
import { ConfigSectionVision } from './ConfigSectionVision';
import { ConfigSectionScheduler } from './ConfigSectionScheduler';
import { ConfigSectionTags } from './ConfigSectionTags';
import { ConfigSectionAdvanced } from './ConfigSectionAdvanced';

export default function ConfigPanel() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [configs, setConfigs] = useState<Record<string, string>>({
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
    log_level: 'INFO',
    modular_tag_process: '',
    modular_tag_ocr: '',
    modular_tag_ocr_fix: '',
    modular_tag_title: '',
    modular_tag_correspondent: '',
    modular_tag_document_type: '',
    modular_tag_tags: '',
    modular_tag_fields: '',
    modular_processed_tag: '',
    auth_enabled: 'false',
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadConfigs();
  }, []);

  const loadConfigs = async () => {
    try {
      const res = await configApi.getAll();
      const loadedConfigs = res.data;
      setConfigs((prev) => ({ ...prev, ...loadedConfigs }));
    } catch (error) {
      console.error('Failed to load configs:', error);
    }
  };

  const handleSave = async (key: string, value: string) => {
    try {
      await configApi.set(key, value);
      setConfigs((prev) => ({ ...prev, [key]: value }));
    } catch (error) {
      console.error(`Failed to save ${key}:`, error);
      throw error;
    }
  };

  const handleSaveAll = async () => {
    setSaving(true);
    if (configs.auth_enabled === 'true' && !configs.paperless_url.trim()) {
      toast.warning(t('config.authRequiresPaperless'));
      setSaving(false);
      return;
    }
    try {
      for (const [key, value] of Object.entries(configs)) {
        if (key === 'auth_enabled') continue;
        await configApi.set(key, value);
      }
      await configApi.set('auth_enabled', configs.auth_enabled);
      if (configs.auth_enabled === 'true') {
        navigate('/login');
        return;
      }
      toast.success(t('config.savedSuccess'));
    } catch (error) {
      console.error('Failed to save configs:', error);
      toast.error(t('config.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center">
        <h1 className="text-2xl font-bold text-gray-900">{t('config.title')}</h1>
      </div>

      <ConfigSectionPaperless config={configs} onSave={handleSave} />
      <ConfigSectionLLM config={configs} onSave={handleSave} />
      {configs.enable_vision === 'true' && (
        <ConfigSectionVision config={configs} onSave={handleSave} />
      )}
      <ConfigSectionScheduler config={configs} onSave={handleSave} />
      <ConfigSectionTags config={configs} onSave={handleSave} />
      <ConfigSectionAdvanced config={configs} onSave={handleSave} />

      <div className="flex justify-end">
        <button
          onClick={handleSaveAll}
          disabled={saving}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? t('config.saving') : t('config.saveConfiguration')}
        </button>
      </div>
    </div>
  );
}
