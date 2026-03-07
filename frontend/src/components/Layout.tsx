import { Outlet, NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { LayoutDashboard, Settings, FileText, Play, MessageCircle } from 'lucide-react';

export default function Layout() {
  const { t, i18n } = useTranslation();

  const navItems = [
    { path: '/dashboard', label: t('nav.dashboard'), icon: LayoutDashboard },
    { path: '/processing', label: t('nav.process'), icon: Play },
    { path: '/chat', label: t('nav.chat'), icon: MessageCircle },
    { path: '/config', label: t('nav.configuration'), icon: Settings },
    { path: '/prompts', label: t('nav.prompts'), icon: FileText },
  ];

  return (
    <div className="min-h-screen flex">
      <aside className="w-64 bg-white border-r border-gray-200">
        <div className="p-6">
          <h1 className="text-xl font-bold text-gray-900">Paperless-AIssist</h1>
          <p className="text-sm text-gray-500">{t('nav.subtitle')}</p>
        </div>
        <nav className="px-4">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-lg mb-1 transition-colors ${
                  isActive
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-600 hover:bg-gray-50'
                }`
              }
            >
              <item.icon size={20} />
              <span className="font-medium">{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="flex-1 flex flex-col">
        <header className="h-12 bg-white border-b border-gray-200 px-6 flex items-center justify-end">
          <div className="flex gap-2">
            {(['en', 'de'] as const).map((lng) => (
              <button
                key={lng}
                onClick={() => i18n.changeLanguage(lng)}
                className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                  i18n.resolvedLanguage === lng
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {t(`language.${lng}`)}
              </button>
            ))}
          </div>
        </header>
        <main className="flex-1 p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
