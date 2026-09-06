import { Monitor, Sun, Moon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Theme, useTheme } from '../contexts/ThemeContext'

const OPTIONS: { value: Theme; Icon: typeof Monitor }[] = [
  { value: 'system', Icon: Monitor },
  { value: 'light', Icon: Sun },
  { value: 'dark', Icon: Moon },
]

export function ThemeSwitch() {
  const { t } = useTranslation()
  const { theme, setTheme } = useTheme()

  return (
    <div className="flex gap-1" role="group" aria-label={t('theme.label')}>
      {OPTIONS.map(({ value, Icon }) => (
        <button
          key={value}
          type="button"
          onClick={() => setTheme(value)}
          aria-pressed={theme === value}
          aria-label={t(`theme.${value}`)}
          title={t(`theme.${value}`)}
          className={`p-1.5 rounded-full transition-colors ${
            theme === value
              ? 'bg-blue-600 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600'
          }`}
        >
          <Icon size={14} />
        </button>
      ))}
    </div>
  )
}
