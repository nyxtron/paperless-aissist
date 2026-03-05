import { Outlet, NavLink } from 'react-router-dom';
import { LayoutDashboard, Settings, FileText, Play, MessageCircle } from 'lucide-react';

const navItems = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/processing', label: 'Process', icon: Play },
  { path: '/chat', label: 'Chat', icon: MessageCircle },
  { path: '/config', label: 'Configuration', icon: Settings },
  { path: '/prompts', label: 'Prompts', icon: FileText },
];

export default function Layout() {
  return (
    <div className="min-h-screen flex">
      <aside className="w-64 bg-white border-r border-gray-200">
        <div className="p-6">
          <h1 className="text-xl font-bold text-gray-900">Paperless-AIssist</h1>
          <p className="text-sm text-gray-500">Document Processing Agent</p>
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
      <main className="flex-1 p-8">
        <Outlet />
      </main>
    </div>
  );
}
