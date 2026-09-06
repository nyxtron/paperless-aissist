import { Outlet, NavLink } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  LayoutDashboard,
  Settings,
  FileText,
  Play,
  MessageCircle,
  ScrollText,
  LogOut,
  Menu,
  X,
  Github,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { appInfoApi } from '../api/client'
import { ThemeSwitch } from './ThemeSwitch'

export default function Layout() {
  const { t, i18n } = useTranslation()
  const { isAuthEnabled, logout } = useAuth()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [appVersion, setAppVersion] = useState('dev')

  useEffect(() => {
    appInfoApi
      .get()
      .then((res) => {
        if (res.data.version) setAppVersion(res.data.version)
      })
      .catch(() => {
        setAppVersion('dev')
      })
  }, [])

  const navItems = [
    { path: '/dashboard', label: t('nav.dashboard'), icon: LayoutDashboard },
    { path: '/processing', label: t('nav.process'), icon: Play },
    { path: '/chat', label: t('nav.chat'), icon: MessageCircle },
    { path: '/config', label: t('nav.configuration'), icon: Settings },
    { path: '/prompts', label: t('nav.prompts'), icon: FileText },
    { path: '/logs', label: t('nav.logs'), icon: ScrollText },
  ]
  const githubRepoUrl = 'https://github.com/nyxtron/paperless-aissist'

  const accountControls = (
    <div className="flex items-center gap-2">
      <ThemeSwitch />
      <span className="w-px h-5 bg-gray-200 dark:bg-gray-700" />
      {(['en', 'de'] as const).map((lng) => (
        <button
          key={lng}
          onClick={() => i18n.changeLanguage(lng)}
          className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
            i18n.resolvedLanguage === lng
              ? 'bg-blue-600 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600'
          }`}
        >
          {t(`language.${lng}`)}
        </button>
      ))}
      {isAuthEnabled && (
        <button
          onClick={logout}
          className="ml-1 px-3 py-1 rounded-full text-sm font-medium text-gray-600 hover:bg-gray-100 flex items-center gap-1 transition-colors dark:text-gray-300 dark:hover:bg-gray-700"
        >
          <LogOut size={14} />
          {t('login.logout')}
        </button>
      )}
    </div>
  )

  const navContent = (
    <>
      <div className="p-6">
        <div className="flex items-center gap-3 mb-1">
          <img src="/icon.png" alt="Paperless-AIssist" className="w-12 h-12 rounded" />
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">Paperless-AIssist</h1>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400">{t('nav.subtitle')}</p>
      </div>
      <nav className="px-4">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            onClick={() => setMobileNavOpen(false)}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-3 rounded-lg mb-1 transition-colors ${
                isActive
                  ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
                  : 'text-gray-600 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-700'
              }`
            }
          >
            <item.icon size={20} />
            <span className="font-medium">{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto px-4 py-4 border-t border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between gap-3 px-3 py-2">
          <a
            href={githubRepoUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-w-0 items-center gap-2 rounded-md text-sm font-medium text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-gray-100"
            aria-label="Paperless-AIssist on GitHub"
          >
            <Github size={16} className="shrink-0" />
            <span className="truncate">GitHub</span>
          </a>
          <span
            className="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-700 dark:text-gray-300"
            title={appVersion}
          >
            {appVersion}
          </span>
        </div>
      </div>
    </>
  )

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 md:flex">
      <aside className="hidden md:flex md:flex-col md:sticky md:top-0 md:h-screen md:overflow-y-auto w-72 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700">
        {navContent}
      </aside>

      <div className="md:hidden sticky top-0 z-30 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="p-6">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <img src="/icon.png" alt="Paperless-AIssist" className="w-10 h-10 rounded" />
              <div className="min-w-0">
                <h1 className="text-base font-bold text-gray-900 dark:text-gray-100 truncate">Paperless-AIssist</h1>
                <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{t('nav.subtitle')}</p>
              </div>
            </div>
            <button
              onClick={() => setMobileNavOpen((prev) => !prev)}
              className="p-2 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-700 hover:bg-gray-50 dark:text-gray-200 dark:hover:bg-gray-700"
              aria-label={mobileNavOpen ? t('common.close') : t('nav.openMenu')}
            >
              {mobileNavOpen ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </div>
        {mobileNavOpen && <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">{navContent}</div>}
      </div>

      <div className="flex-1 flex flex-col">
        <header className="h-14 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-4 md:px-6 flex items-center justify-end">
          {accountControls}
        </header>
        <main className="flex-1 p-4 md:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
