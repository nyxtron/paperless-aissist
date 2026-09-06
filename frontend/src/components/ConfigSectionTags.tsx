import { useTranslation } from 'react-i18next'
import { Tag } from 'lucide-react'
import { ConfigSectionProps } from './ConfigSectionProps'
import { fieldClass, labelClass, hintClass } from './fieldStyles'
import { MODULAR_TAG_DEFAULTS } from '../constants'

// fieldStyles.ts is shared across several config sections and stays untouched here;
// these wrap the shared constants with the dark-mode variants for this file's fields.
const fieldClassDark = `${fieldClass} dark:bg-gray-900 dark:border-gray-600 dark:text-gray-100 dark:placeholder-gray-500`
const labelClassDark = `${labelClass} dark:text-gray-200`
const hintClassDark = `${hintClass} dark:text-gray-400`

export function ConfigSectionTags({ config, onSave }: ConfigSectionProps) {
  const { t } = useTranslation()

  const handleChange = async (key: string, value: string) => {
    await onSave(key, value)
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow dark:shadow-none p-6 space-y-4">
      <div className="flex items-center gap-2 border-b border-gray-200 dark:border-gray-700 pb-3 mb-4">
        <Tag size={18} className="text-blue-600 dark:text-blue-400" />
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100">{t('config.modularSection')}</h2>
      </div>
      <p className="text-sm text-gray-500 dark:text-gray-400 -mt-2">{t('config.modularSectionHint')}</p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className={labelClassDark}>{t('config.modularTagProcess')}</label>
          <input
            type="text"
            className={fieldClassDark}
            value={config.modular_tag_process || ''}
            placeholder={MODULAR_TAG_DEFAULTS.modular_tag_process}
            onChange={(e) => handleChange('modular_tag_process', e.target.value)}
          />
          <p className={hintClassDark}>{t('config.modularTagProcessHint')}</p>
        </div>
        <div>
          <label className={labelClassDark}>{t('config.modularTagOcr')}</label>
          <input
            type="text"
            className={fieldClassDark}
            value={config.modular_tag_ocr || ''}
            placeholder={MODULAR_TAG_DEFAULTS.modular_tag_ocr}
            onChange={(e) => handleChange('modular_tag_ocr', e.target.value)}
          />
          <p className={hintClassDark}>{t('config.modularTagOcrHint')}</p>
        </div>
        <div>
          <label className={labelClassDark}>{t('config.modularTagOcrFix')}</label>
          <input
            type="text"
            className={fieldClassDark}
            value={config.modular_tag_ocr_fix || ''}
            placeholder={MODULAR_TAG_DEFAULTS.modular_tag_ocr_fix}
            onChange={(e) => handleChange('modular_tag_ocr_fix', e.target.value)}
          />
          <p className={hintClassDark}>{t('config.modularTagOcrFixHint')}</p>
        </div>
        <div>
          <label className={labelClassDark}>{t('config.modularTagDate')}</label>
          <input
            type="text"
            className={fieldClassDark}
            value={config.modular_tag_date || ''}
            placeholder={MODULAR_TAG_DEFAULTS.modular_tag_date}
            onChange={(e) => handleChange('modular_tag_date', e.target.value)}
          />
          <p className={hintClassDark}>{t('config.modularTagDateHint')}</p>
        </div>
        <div>
          <label className={labelClassDark}>{t('config.modularTagTitle')}</label>
          <input
            type="text"
            className={fieldClassDark}
            value={config.modular_tag_title || ''}
            placeholder={MODULAR_TAG_DEFAULTS.modular_tag_title}
            onChange={(e) => handleChange('modular_tag_title', e.target.value)}
          />
          <p className={hintClassDark}>{t('config.modularTagTitleHint')}</p>
        </div>
        <div>
          <label className={labelClassDark}>{t('config.modularTagCorrespondent')}</label>
          <input
            type="text"
            className={fieldClassDark}
            value={config.modular_tag_correspondent || ''}
            placeholder={MODULAR_TAG_DEFAULTS.modular_tag_correspondent}
            onChange={(e) => handleChange('modular_tag_correspondent', e.target.value)}
          />
          <p className={hintClassDark}>{t('config.modularTagCorrespondentHint')}</p>
        </div>
        <div>
          <label className={labelClassDark}>{t('config.modularTagDocumentType')}</label>
          <input
            type="text"
            className={fieldClassDark}
            value={config.modular_tag_document_type || ''}
            placeholder={MODULAR_TAG_DEFAULTS.modular_tag_document_type}
            onChange={(e) => handleChange('modular_tag_document_type', e.target.value)}
          />
          <p className={hintClassDark}>{t('config.modularTagDocumentTypeHint')}</p>
        </div>
        <div>
          <label className={labelClassDark}>{t('config.modularTagTags')}</label>
          <input
            type="text"
            className={fieldClassDark}
            value={config.modular_tag_tags || ''}
            placeholder={MODULAR_TAG_DEFAULTS.modular_tag_tags}
            onChange={(e) => handleChange('modular_tag_tags', e.target.value)}
          />
          <p className={hintClassDark}>{t('config.modularTagTagsHint')}</p>
        </div>
        <div>
          <label className={labelClassDark}>{t('config.modularTagFields')}</label>
          <input
            type="text"
            className={fieldClassDark}
            value={config.modular_tag_fields || ''}
            placeholder={MODULAR_TAG_DEFAULTS.modular_tag_fields}
            onChange={(e) => handleChange('modular_tag_fields', e.target.value)}
          />
          <p className={hintClassDark}>{t('config.modularTagFieldsHint')}</p>
        </div>
      </div>
    </div>
  )
}
