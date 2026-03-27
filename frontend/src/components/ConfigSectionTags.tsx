import { useTranslation } from 'react-i18next';
import { Tag } from 'lucide-react';

interface ConfigSectionProps {
  config: Record<string, string>;
  onSave: (key: string, value: string) => Promise<void>;
  onTest?: (key: string) => Promise<boolean>;
}

const MODULAR_TAG_DEFAULTS: Record<string, string> = {
  modular_tag_ocr: 'ai-ocr',
  modular_tag_title: 'ai-title',
  modular_tag_correspondent: 'ai-correspondent',
  modular_tag_document_type: 'ai-document-type',
  modular_tag_tags: 'ai-tags',
  modular_tag_fields: 'ai-fields',
  modular_tag_process: 'ai-process',
  modular_tag_ocr_fix: 'ai-ocr-fix',
  modular_processed_tag: 'ai-processed',
};

export function ConfigSectionTags({ config, onSave }: ConfigSectionProps) {
  const { t } = useTranslation();

  const field = 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500';
  const label = 'block text-sm font-medium text-gray-700 mb-1';
  const hint = 'text-xs text-gray-500 mt-1';

  const handleChange = async (key: string, value: string) => {
    await onSave(key, value);
  };

  return (
    <div className="bg-white rounded-lg shadow p-6 space-y-4">
      <div className="flex items-center gap-2 border-b pb-3 mb-4">
        <Tag size={18} className="text-blue-600" />
        <h2 className="text-lg font-semibold text-gray-800">{t('config.modularSection')}</h2>
      </div>
      <p className="text-sm text-gray-500 -mt-2">{t('config.modularSectionHint')}</p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className={label}>{t('config.modularTagProcess')}</label>
          <input
            type="text"
            className={field}
            value={config.modular_tag_process || ''}
            placeholder={MODULAR_TAG_DEFAULTS.modular_tag_process}
            onChange={(e) => handleChange('modular_tag_process', e.target.value)}
          />
          <p className={hint}>{t('config.modularTagProcessHint')}</p>
        </div>
        <div>
          <label className={label}>{t('config.modularTagOcr')}</label>
          <input
            type="text"
            className={field}
            value={config.modular_tag_ocr || ''}
            placeholder={MODULAR_TAG_DEFAULTS.modular_tag_ocr}
            onChange={(e) => handleChange('modular_tag_ocr', e.target.value)}
          />
          <p className={hint}>{t('config.modularTagOcrHint')}</p>
        </div>
        <div>
          <label className={label}>{t('config.modularTagOcrFix')}</label>
          <input
            type="text"
            className={field}
            value={config.modular_tag_ocr_fix || ''}
            placeholder={MODULAR_TAG_DEFAULTS.modular_tag_ocr_fix}
            onChange={(e) => handleChange('modular_tag_ocr_fix', e.target.value)}
          />
          <p className={hint}>{t('config.modularTagOcrFixHint')}</p>
        </div>
        <div>
          <label className={label}>{t('config.modularTagTitle')}</label>
          <input
            type="text"
            className={field}
            value={config.modular_tag_title || ''}
            placeholder={MODULAR_TAG_DEFAULTS.modular_tag_title}
            onChange={(e) => handleChange('modular_tag_title', e.target.value)}
          />
          <p className={hint}>{t('config.modularTagTitleHint')}</p>
        </div>
        <div>
          <label className={label}>{t('config.modularTagCorrespondent')}</label>
          <input
            type="text"
            className={field}
            value={config.modular_tag_correspondent || ''}
            placeholder={MODULAR_TAG_DEFAULTS.modular_tag_correspondent}
            onChange={(e) => handleChange('modular_tag_correspondent', e.target.value)}
          />
          <p className={hint}>{t('config.modularTagCorrespondentHint')}</p>
        </div>
        <div>
          <label className={label}>{t('config.modularTagDocumentType')}</label>
          <input
            type="text"
            className={field}
            value={config.modular_tag_document_type || ''}
            placeholder={MODULAR_TAG_DEFAULTS.modular_tag_document_type}
            onChange={(e) => handleChange('modular_tag_document_type', e.target.value)}
          />
          <p className={hint}>{t('config.modularTagDocumentTypeHint')}</p>
        </div>
        <div>
          <label className={label}>{t('config.modularTagTags')}</label>
          <input
            type="text"
            className={field}
            value={config.modular_tag_tags || ''}
            placeholder={MODULAR_TAG_DEFAULTS.modular_tag_tags}
            onChange={(e) => handleChange('modular_tag_tags', e.target.value)}
          />
          <p className={hint}>{t('config.modularTagTagsHint')}</p>
        </div>
        <div>
          <label className={label}>{t('config.modularTagFields')}</label>
          <input
            type="text"
            className={field}
            value={config.modular_tag_fields || ''}
            placeholder={MODULAR_TAG_DEFAULTS.modular_tag_fields}
            onChange={(e) => handleChange('modular_tag_fields', e.target.value)}
          />
          <p className={hint}>{t('config.modularTagFieldsHint')}</p>
        </div>
        <div>
          <label className={label}>{t('config.modularProcessedTag')}</label>
          <input
            type="text"
            className={field}
            value={config.modular_processed_tag || ''}
            placeholder={MODULAR_TAG_DEFAULTS.modular_processed_tag}
            onChange={(e) => handleChange('modular_processed_tag', e.target.value)}
          />
          <p className={hint}>{t('config.modularProcessedTagHint')}</p>
        </div>
      </div>
    </div>
  );
}
