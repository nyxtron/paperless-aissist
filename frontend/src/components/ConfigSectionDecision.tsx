import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { configApi, documentsApi } from '../api/client'
import { extractApiError } from '../api/errorUtils'
import { ConfigSectionProps } from './ConfigSectionProps'
import { fieldClass, labelClass, hintClass } from './fieldStyles'

const FIELDS = ['correspondent', 'document_type'] as const
const FORMATS = ['auto', 'letters', 'nimble', 'systemone'] as const

const TOGGLE_LABELS = {
  correspondent: 'config.decisionCorrespondent',
  document_type: 'config.decisionDocumentType',
} as const

const FORMAT_LABELS = {
  auto: 'config.decisionFormatAuto',
  letters: 'config.decisionFormatLetters',
  nimble: 'config.decisionFormatNimble',
  systemone: 'config.decisionFormatSystemOne',
} as const

const DEFAULT_QUESTIONS = {
  correspondent: 'Who sent this document (the correspondent)?',
  document_type: 'What type of document is this?',
} as const

const REVIEW_TAG_DEFAULT = 'ai-review'
const TAG_CHECK_DELAY_MS = 500

const warnClass = 'text-xs text-amber-700 dark:text-amber-300 mt-1'
const numberClass =
  'px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-500'

// Grok gives no token probabilities; Nimble and SystemOne only run on Ollama.
const formatUsable = (provider: string, format: string) => {
  if (provider === 'grok') return false
  if (provider !== 'ollama' && (format === 'nimble' || format === 'systemone')) return false
  return true
}

const modelPlaceholder = (provider: string) => {
  if (provider === 'openai') return 'gpt-4o-mini'
  if (provider === 'grok') return 'grok-3-mini'
  if (provider === 'openrouter') return 'openai/gpt-4o-mini'
  return 'nimble'
}

const apiBasePlaceholder = (provider: string) => {
  if (provider === 'openai') return 'https://api.openai.com/v1'
  if (provider === 'grok') return 'https://api.x.ai/v1'
  if (provider === 'openrouter') return 'https://openrouter.ai/api/v1'
  return 'http://localhost:11434'
}

type TagCheck = { name: string; exists: boolean | null }

export function ConfigSectionDecision({
  config,
  onSave,
  secretsSet,
  onSecretsChanged,
  onSecretRemoved,
}: ConfigSectionProps) {
  const { t } = useTranslation()
  const [tagCheck, setTagCheck] = useState<TagCheck | null>(null)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [testDetail, setTestDetail] = useState<string | null>(null)
  const [testRequest, setTestRequest] = useState<string | null>(null)
  const [showRequest, setShowRequest] = useState(false)
  const checkedOnce = useRef(false)

  const anyOn = FIELDS.some((f) => (config[`decision_${f}`] || 'false') === 'true')
  const ownProvider = config.llm_provider_decision || ''
  const inherited = !ownProvider
  const provider = ownProvider || config.llm_provider || 'ollama'
  const format = config.decision_format || 'auto'
  const reviewTag = (config.review_tag || '').trim() || REVIEW_TAG_DEFAULT
  const secretStored = (key: string) => Boolean(secretsSet?.includes(key))

  // Plain tag list, no forced refresh; while the name is being typed, wait for a pause.
  useEffect(() => {
    let alive = true
    const check = () => {
      checkedOnce.current = true
      documentsApi
        .getTags()
        .then((res) => {
          const tags = (res.data?.tags ?? []) as Array<{ name: string }>
          const exists = tags.some((tag) => tag.name === reviewTag)
          if (alive) setTagCheck({ name: reviewTag, exists })
        })
        .catch(() => {
          if (alive) setTagCheck({ name: reviewTag, exists: null })
        })
    }
    const timer = setTimeout(check, checkedOnce.current ? TAG_CHECK_DELAY_MS : 0)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [reviewTag])

  const save = (key: string, value: string) => void onSave(key, value)

  const removeKey = async () => {
    onSecretRemoved?.('llm_api_key_decision')
    try {
      await configApi.delete('llm_api_key_decision')
      toast.success(t('config.decisionKeyRemoved'))
      onSecretsChanged?.()
    } catch {
      toast.error(t('config.saveFailed'))
    }
  }

  const runTest = async () => {
    setTesting(true)
    setTestResult(null)
    setTestDetail(null)
    setTestRequest(null)
    try {
      const { data } = await configApi.testDecision()
      setTestRequest(data.request ?? null)
      if (data.success) {
        const p = data.probability == null ? '–' : `${(data.probability * 100).toFixed(1)}%`
        setTestResult(
          t('config.decisionTestOk', {
            method: data.method,
            model: data.model,
            choice: data.choice ?? '',
            p,
          }),
        )
      } else if (data.fallback_reason) {
        setTestResult(
          t('config.decisionTestFallback', {
            reason: t(`decision.fallback.${data.fallback_reason}`),
          }),
        )
        setTestDetail(data.fallback_detail ?? null)
      } else {
        setTestResult(t('config.decisionTestFailed', { message: data.message ?? '' }))
      }
      if (data.review_tag) setTagCheck(data.review_tag)
    } catch (error) {
      setTestResult(t('config.decisionTestFailed', { message: extractApiError(error).message }))
    } finally {
      setTesting(false)
    }
  }

  // A result for a name that has since been edited says nothing about the current one.
  const tagStatus = tagCheck?.name === reviewTag ? tagCheck.exists : undefined

  return (
    <div className="bg-blue-50/50 dark:bg-blue-950/40 border border-blue-100 dark:border-blue-900 rounded-lg shadow-sm dark:shadow-none p-6 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-blue-100 dark:border-blue-900 pb-3 mb-4">
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">
          {t('config.decisionSection')}
        </h3>
        <span
          className={`text-xs px-2 py-1 rounded-full ${
            anyOn
              ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300'
              : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
          }`}
        >
          {anyOn ? t('common.enabled') : t('common.disabled')}
        </span>
      </div>
      <p className={hintClass}>{t('config.decisionSectionHint')}</p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {FIELDS.map((field) => (
          <div key={field} className="space-y-2">
            <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200">
              <input
                type="checkbox"
                checked={(config[`decision_${field}`] || 'false') === 'true'}
                onChange={(e) => save(`decision_${field}`, e.target.checked ? 'true' : 'false')}
              />
              {t(TOGGLE_LABELS[field])}
            </label>
            <div>
              <label className={labelClass} htmlFor={`decision-threshold-${field}`}>
                {t('config.decisionThreshold', { field: t(`decision.field.${field}`) })}
              </label>
              <input
                id={`decision-threshold-${field}`}
                type="number"
                min="0.5"
                max="1"
                step="0.01"
                value={config[`decision_threshold_${field}`] || '0.9'}
                onChange={(e) => save(`decision_threshold_${field}`, e.target.value)}
                className={`w-32 ${numberClass}`}
              />
              <p className={hintClass}>{t('config.decisionThresholdHint')}</p>
            </div>
            <div>
              <label className={labelClass} htmlFor={`decision-question-${field}`}>
                {t('config.decisionQuestion', { field: t(`decision.field.${field}`) })}
              </label>
              <input
                id={`decision-question-${field}`}
                type="text"
                value={config[`decision_question_${field}`] || ''}
                placeholder={DEFAULT_QUESTIONS[field]}
                onChange={(e) => save(`decision_question_${field}`, e.target.value)}
                className={fieldClass}
              />
            </div>
          </div>
        ))}

        <div>
          <label className={labelClass} htmlFor="decision-review-tag">
            {t('config.reviewTag')}
          </label>
          <input
            id="decision-review-tag"
            type="text"
            value={config.review_tag || ''}
            placeholder={REVIEW_TAG_DEFAULT}
            onChange={(e) => save('review_tag', e.target.value)}
            className={fieldClass}
          />
          <p className={hintClass}>{t('config.reviewTagHint')}</p>
          {tagStatus === false && (
            <p className={warnClass}>{t('config.reviewTagMissing', { tag: reviewTag })}</p>
          )}
          {tagStatus === true && (
            <p className={hintClass}>{t('config.reviewTagPresent', { tag: reviewTag })}</p>
          )}
          {tagStatus === null && <p className={hintClass}>{t('config.reviewTagUnknown')}</p>}
        </div>

        <div>
          <label className={labelClass} htmlFor="decision-format">
            {t('config.decisionFormat')}
          </label>
          <select
            id="decision-format"
            value={format}
            onChange={(e) => save('decision_format', e.target.value)}
            className={fieldClass}
          >
            {FORMATS.map((f) => (
              <option key={f} value={f}>
                {t(FORMAT_LABELS[f])}
              </option>
            ))}
          </select>
          <p className={hintClass}>{t('config.decisionFormatHint')}</p>
          {!formatUsable(provider, format) && (
            <p className={warnClass}>{t('config.decisionFormatUnusable')}</p>
          )}
        </div>
      </div>

      <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-100 pt-2">
        {t('config.decisionModelSection')}
      </h4>
      <p className={hintClass}>
        {inherited ? t('config.decisionInherited') : t('config.decisionModelHint')}
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className={labelClass} htmlFor="decision-provider">
            {t('config.provider')}
          </label>
          <select
            id="decision-provider"
            value={ownProvider}
            onChange={(e) => save('llm_provider_decision', e.target.value)}
            className={fieldClass}
          >
            <option value="">{t('config.decisionInheritedOption')}</option>
            <option value="ollama">Ollama</option>
            <option value="openai">OpenAI / LM Studio / vLLM</option>
            <option value="openrouter">OpenRouter</option>
            <option value="grok">Grok (xAI)</option>
          </select>
        </div>
        <div>
          <label className={labelClass} htmlFor="decision-model">
            {t('config.model')}
          </label>
          <input
            id="decision-model"
            type="text"
            value={config.llm_model_decision || ''}
            placeholder={inherited ? config.llm_model || '' : modelPlaceholder(ownProvider)}
            onChange={(e) => save('llm_model_decision', e.target.value)}
            className={fieldClass}
          />
          {!inherited && !config.llm_model_decision && (
            <p className={warnClass}>{t('config.decisionModelRequired')}</p>
          )}
        </div>
        <div>
          <label className={labelClass} htmlFor="decision-api-base">
            {t('config.apiBaseUrl')}
          </label>
          <input
            id="decision-api-base"
            type="text"
            disabled={inherited}
            value={inherited ? '' : config.llm_api_base_decision || ''}
            placeholder={inherited ? config.llm_api_base || '' : apiBasePlaceholder(ownProvider)}
            onChange={(e) => save('llm_api_base_decision', e.target.value)}
            className={`${fieldClass} disabled:opacity-60`}
          />
          {!inherited && ownProvider !== 'openrouter' && !config.llm_api_base_decision && (
            <p className={warnClass}>{t('config.decisionUrlRequired')}</p>
          )}
        </div>
        <div>
          <label className={labelClass} htmlFor="decision-api-key">
            {t('config.apiKey')}
          </label>
          <input
            id="decision-api-key"
            type="password"
            disabled={inherited}
            value={inherited ? '' : config.llm_api_key_decision || ''}
            placeholder={
              secretStored(inherited ? 'llm_api_key' : 'llm_api_key_decision')
                ? t('config.alreadySetPlaceholder')
                : ''
            }
            onChange={(e) => save('llm_api_key_decision', e.target.value)}
            className={`${fieldClass} disabled:opacity-60`}
          />
          {secretStored('llm_api_key_decision') && (
            <button
              type="button"
              onClick={removeKey}
              className="text-xs underline mt-1 text-gray-600 dark:text-gray-300"
            >
              {t('config.decisionRemoveKey')}
            </button>
          )}
        </div>
        <div>
          <label className={labelClass} htmlFor="decision-timeout">
            {t('config.llmTimeout')}
          </label>
          <input
            id="decision-timeout"
            type="number"
            min="30"
            max="3600"
            value={config.llm_timeout_decision || ''}
            placeholder={config.llm_timeout || '600'}
            onChange={(e) => save('llm_timeout_decision', e.target.value)}
            className={`w-32 ${numberClass}`}
          />
        </div>
        <div>
          <label className={labelClass} htmlFor="decision-num-ctx">
            {t('config.decisionContextWindow')}
          </label>
          <input
            id="decision-num-ctx"
            type="number"
            min="1"
            step="1"
            value={config.llm_num_ctx_decision || ''}
            placeholder={config.llm_num_ctx || '16384'}
            onChange={(e) => save('llm_num_ctx_decision', e.target.value)}
            className={`w-40 ${numberClass}`}
          />
        </div>
      </div>

      <div className="pt-2">
        <button
          type="button"
          onClick={runTest}
          disabled={testing}
          className="px-3 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {testing ? t('config.decisionTesting') : t('config.decisionTest')}
        </button>
        {testResult && (
          <p className="mt-2 text-sm text-gray-700 dark:text-gray-200">{testResult}</p>
        )}
        {testDetail && (
          <p className="mt-1 text-xs break-all text-gray-600 dark:text-gray-300">{testDetail}</p>
        )}
        {testRequest && (
          <div className="mt-1 text-xs text-gray-600 dark:text-gray-300">
            <button type="button" className="underline" onClick={() => setShowRequest((v) => !v)}>
              {showRequest ? t('decision.note.hideRequest') : t('decision.note.showRequest')}
            </button>
            {showRequest && (
              <pre className="mt-1 whitespace-pre-wrap break-words">{testRequest}</pre>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
