import { useTranslation } from 'react-i18next'
import { AlertTriangle } from 'lucide-react'

export interface PromptCut {
  evaluated: number
  window: number | null
}

// Ollama cuts a prompt that does not fit its context window without an error,
// so the step ran on half a prompt. Shown wherever a step's result is shown.
export function PromptCutNote({ cut }: { cut: PromptCut }) {
  const { t } = useTranslation()
  return (
    <p className="mt-1 flex items-start gap-1 text-xs text-amber-700 dark:text-amber-300">
      <AlertTriangle size={12} className="mt-0.5 shrink-0" />
      <span>
        {cut.window
          ? t('processing.promptCut', { evaluated: cut.evaluated, window: cut.window })
          : t('processing.promptCutNoWindow', { evaluated: cut.evaluated })}
      </span>
    </p>
  )
}
