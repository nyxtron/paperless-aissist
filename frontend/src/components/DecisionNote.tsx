import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import type { DecisionDetails } from '../api/types'

// The backend's label for the extra option that names none of the list.
const NONE_LABEL = 'None of these'

// Floored, so a probability just under the threshold never prints as the threshold.
const pct = (p: number | null) => (p === null ? '–' : `${(Math.floor(p * 1000) / 10).toFixed(1)}%`)
const pctThreshold = (t: number) => `${Math.round(t * 100)}%`

// One line per decided field, wherever a step's result is shown: what was
// chosen and how sure, or why the field was left for a look.
export function DecisionNote({
  decision,
  showRequest = false,
}: {
  decision: DecisionDetails
  showRequest?: boolean
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const amber = decision.outcome === 'review' || decision.outcome === 'fallback'
  const color = amber ? 'text-amber-700 dark:text-amber-300' : 'text-gray-600 dark:text-gray-300'

  let line: string
  if (decision.outcome === 'fallback') {
    line = t('decision.note.fallback', {
      reason: t(`decision.fallback.${decision.fallback_reason ?? 'no_logprobs'}`),
    })
  } else if (decision.outcome === 'review') {
    const reason = t(`decision.reason.${decision.reason ?? 'below_threshold'}`)
    // Most reasons fire at or above the threshold, so a best guess is only
    // worth naming when it is a real name that fell short.
    const nameFellShort =
      decision.choice &&
      decision.choice !== NONE_LABEL &&
      decision.probability !== null &&
      decision.probability < decision.threshold
    line = nameFellShort
      ? t('decision.note.review', {
          reason,
          choice: decision.choice,
          p: pct(decision.probability),
          threshold: pctThreshold(decision.threshold),
        })
      : t('decision.note.reviewNone', { reason })
  } else if (decision.outcome === 'would_create') {
    line = t('decision.note.wouldCreate', { name: decision.choice ?? '' })
  } else {
    line = t('decision.note.decided', {
      choice: decision.choice ?? '',
      p: pct(decision.probability),
      threshold: pctThreshold(decision.threshold),
      model: decision.model,
    })
  }
  const request = decision.request?.full ?? decision.request?.rendered
  // What else the deciding round leaned to, so a review shows what it was between.
  // top is the last round while the main line's p is the weakest round, so an
  // option above that p would read as the better answer and is left out.
  const alternatives =
    decision.outcome === 'review'
      ? (decision.top ?? [])
          .filter(
            (option) =>
              option.name !== decision.choice &&
              option.p >= 0.01 &&
              (decision.probability === null || option.p < decision.probability),
          )
          .slice(0, 2)
          .map(
            (option) =>
              `${option.name === NONE_LABEL ? t('decision.note.noneOfThese') : option.name} ${pct(option.p)}`,
          )
      : []

  return (
    <div className={`mt-1 text-xs ${color}`}>
      <p className="flex items-start gap-1">
        {amber ? (
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
        ) : (
          <CheckCircle2 size={12} className="mt-0.5 shrink-0" />
        )}
        <span>{line}</span>
      </p>
      {alternatives.length > 0 && (
        <p className="ml-4">
          {t('decision.note.alternatives', { list: alternatives.join(' · ') })}
        </p>
      )}
      {decision.outcome === 'review' && decision.suggestion && (
        <p className="ml-4">{t('decision.note.suggestion', { name: decision.suggestion })}</p>
      )}
      {decision.outcome === 'fallback' && decision.fallback_detail && (
        <p className="ml-4 break-all">{decision.fallback_detail}</p>
      )}
      {showRequest && request && (
        <div className="ml-4">
          <button type="button" className="underline" onClick={() => setOpen((v) => !v)}>
            {open ? t('decision.note.hideRequest') : t('decision.note.showRequest')}
          </button>
          {open && (
            <pre className="mt-1 whitespace-pre-wrap break-words text-[11px] text-gray-700 dark:text-gray-200">
              {request}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}
