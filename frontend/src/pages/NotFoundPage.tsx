import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-4 text-white">
      <h1 className="text-6xl font-bold text-gray-600">404</h1>
      <p className="text-gray-400">Страница не найдена</p>
      <Link to="/dashboard" className="text-indigo-400 hover:underline">
        На главную
      </Link>
    </div>
  );
}
