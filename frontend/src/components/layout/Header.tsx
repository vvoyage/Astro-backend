import { Link } from 'react-router-dom';
import { useAuth } from '@/auth/useAuth';

export default function Header() {
  const { user, logout } = useAuth();

  return (
    <header className="flex items-center justify-between border-b border-gray-800 px-4 py-3">
      <Link to="/dashboard" className="text-lg font-bold text-white">
        Astro Builder
      </Link>
      <div className="flex items-center gap-4">
        <span className="text-sm text-gray-400">{user?.profile?.email}</span>
        <button
          onClick={logout}
          className="rounded px-3 py-1 text-sm text-gray-400 hover:text-white transition-colors"
        >
          Выйти
        </button>
      </div>
    </header>
  );
}
