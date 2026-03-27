import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { documentsApi } from '../api/client';
import { Server, RefreshCw, CheckCircle, XCircle } from 'lucide-react';

interface PaperlessTag {
  id: number;
  name: string;
}

interface PaperlessItem {
  id: number;
  name: string;
}

interface ConfigSectionProps {
  config: Record<string, string>;
  onSave: (key: string, value: string) => Promise<void>;
  onTest?: (key: string) => Promise<boolean>;
}

interface PaperlessStatus {
  connected: boolean;
  error: string | null;
  tags: PaperlessTag[];
  correspondents: PaperlessItem[];
}

export function ConfigSectionPaperless({ config, onSave }: ConfigSectionProps) {
  const { t } = useTranslation();
  const [testing, setTesting] = useState(false);
  const [status, setStatus] = useState<PaperlessStatus>({
    connected: false,
    error: null,
    tags: [],
    correspondents: [],
  });

  const field = 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500';
  const label = 'block text-sm font-medium text-gray-700 mb-1';
  const hint = 'text-xs text-gray-500 mt-1';

  useEffect(() => {
    if (config.paperless_url && config.paperless_token && status.tags.length === 0) {
      handleTest();
    }
  }, [config.paperless_url, config.paperless_token]);

  const handleTest = async () => {
    setTesting(true);
    setStatus((prev) => ({ ...prev, error: null }));
    try {
      const res = await documentsApi.getTags();
      setStatus({
        connected: true,
        error: null,
        tags: res.data.tags || [],
        correspondents: res.data.correspondents || [],
      });
    } catch (error: any) {
      const errorMsg = error.response?.data?.detail || error.message;
      const i18nKey = 'config.paperlessNotConfigured';
      const translatedMsg = errorMsg === 'Paperless URL and Token must be configured' 
        ? t(i18nKey) 
        : errorMsg;
      setStatus((prev) => ({
        ...prev,
        connected: false,
        error: translatedMsg,
      }));
    } finally {
      setTesting(false);
    }
  };

  const handleChange = async (key: string, value: string) => {
    await onSave(key, value);
  };

  const getTagOptions = (savedValue: string) => {
    if (status.tags.length > 0) {
      return status.tags;
    }
    if (savedValue) {
      return [{ id: -1, name: savedValue }];
    }
    return [];
  };

  return (
    <div className="bg-white rounded-lg shadow p-6 space-y-4">
      <div className="flex items-center gap-2 border-b pb-3 mb-4">
        <Server size={18} className="text-blue-600" />
        <h2 className="text-lg font-semibold text-gray-800">{t('config.paperlessSection')}</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className={label}>{t('config.paperlessUrl')}</label>
          <input
            type="text"
            value={config.paperless_url || ''}
            onChange={(e) => handleChange('paperless_url', e.target.value)}
            placeholder="http://localhost:8000"
            className={field}
          />
        </div>
        <div>
          <label className={label}>{t('config.apiToken')}</label>
          <input
            type="password"
            value={config.paperless_token || ''}
            onChange={(e) => handleChange('paperless_token', e.target.value)}
            placeholder={t('config.apiTokenPlaceholder')}
            className={field}
          />
        </div>
      </div>

      <div>
        <button
          onClick={handleTest}
          disabled={testing}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {testing ? <RefreshCw size={16} className="animate-spin" /> : <Server size={16} />}
          {testing ? t('config.connecting') : t('config.connect')}
        </button>
      </div>

      {status.connected && (
        <div className="flex items-center gap-2 px-3 py-2 bg-green-50 text-green-700 rounded-lg text-sm">
          <CheckCircle size={16} />
          {t('config.connectedBadge', { tags: status.tags.length, correspondents: status.correspondents.length })}
        </div>
      )}

      {status.error && (
        <div className="flex items-center gap-2 px-3 py-2 bg-red-50 text-red-700 rounded-lg text-sm">
          <XCircle size={16} />
          {status.error}
        </div>
      )}

      <div className="border-t pt-4 space-y-4">
        {!status.connected && status.tags.length === 0 && (
          <p className="text-xs text-gray-400 italic">{t('config.notConnectedHint')}</p>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={label}>{t('config.processTag')}</label>
            <select
              value={config.process_tag || ''}
              onChange={(e) => handleChange('process_tag', e.target.value)}
              className={field}
            >
              <option value="">{t('common.selectTag')}</option>
              {getTagOptions(config.process_tag).map((tag) => (
                <option key={tag.id} value={tag.name}>{tag.name}</option>
              ))}
            </select>
            <p className={hint}>{t('config.processTagHint')}</p>
          </div>
          <div>
            <label className={label}>{t('config.processedTag')}</label>
            <select
              value={config.processed_tag || ''}
              onChange={(e) => handleChange('processed_tag', e.target.value)}
              className={field}
            >
              <option value="">{t('common.selectTag')}</option>
              {getTagOptions(config.processed_tag).map((tag) => (
                <option key={tag.id} value={tag.name}>{tag.name}</option>
              ))}
            </select>
            <p className={hint}>{t('config.processedTagHint')}</p>
          </div>
        </div>

        <div>
          <label className={label}>{t('config.tagBlacklist')}</label>
          <input
            type="text"
            value={config.tag_blacklist || ''}
            onChange={(e) => handleChange('tag_blacklist', e.target.value)}
            placeholder={t('config.tagBlacklistPlaceholder')}
            className={field}
          />
          <p className={hint}>{t('config.tagBlacklistHint')}</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={label}>{t('config.forceOcrTag')}</label>
            <select
              value={config.force_ocr_tag || ''}
              onChange={(e) => handleChange('force_ocr_tag', e.target.value)}
              className={field}
            >
              <option value="">{t('common.none')}</option>
              {getTagOptions(config.force_ocr_tag).map((tag) => (
                <option key={tag.id} value={tag.name}>{tag.name}</option>
              ))}
            </select>
            <p className={hint}>{t('config.forceOcrTagHint')}</p>
          </div>
          <div>
            <label className={label}>{t('config.forceOcrFixTag')}</label>
            <select
              value={config.force_ocr_fix_tag || ''}
              onChange={(e) => handleChange('force_ocr_fix_tag', e.target.value)}
              className={field}
            >
              <option value="">{t('common.none')}</option>
              {getTagOptions(config.force_ocr_fix_tag).map((tag) => (
                <option key={tag.id} value={tag.name}>{tag.name}</option>
              ))}
            </select>
            <p className={hint}>{t('config.forceOcrFixTagHint')}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
