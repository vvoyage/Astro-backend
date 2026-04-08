import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '@/auth/useAuth';
import { registerUser } from '@/api/auth';
import type { AxiosError } from 'axios';

export default function RegisterPage() {
  const { user, isLoading, loginWithCredentials } = useAuth();
  const navigate = useNavigate();

  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isPending, setIsPending] = useState(false);

  useEffect(() => {
    if (!isLoading && user) navigate('/dashboard', { replace: true });
  }, [user, isLoading, navigate]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsPending(true);
    try {
      await registerUser({ email, password, first_name: firstName, last_name: lastName });
    } catch (err: unknown) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      const msg =
        axiosErr.response?.data?.detail ??
        (err as { error_description?: string })?.error_description ??
        'Ошибка регистрации';
      toast.error(msg);
      setIsPending(false);
      return;
    }

    // Auto-login after registration — если упало, просто редиректим на /login
    try {
      await loginWithCredentials(email, password);
      navigate('/dashboard', { replace: true });
    } catch {
      toast.success('Аккаунт создан! Войдите с вашими данными.');
      navigate('/login', { replace: true });
    } finally {
      setIsPending(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-950 px-4">
      <div className="w-full max-w-sm space-y-8">
        {/* Logo / title */}
        <div className="text-center">
          <h1 className="text-3xl font-bold text-white">Astro Builder</h1>
          <p className="mt-2 text-sm text-gray-400">Создайте аккаунт</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="flex gap-3">
            <div className="flex-1 space-y-1">
              <label htmlFor="firstName" className="block text-sm font-medium text-gray-300">
                Имя
              </label>
              <input
                id="firstName"
                type="text"
                autoComplete="given-name"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                className="w-full rounded-lg border border-gray-700 bg-gray-900 px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none transition focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                placeholder="Иван"
              />
            </div>
            <div className="flex-1 space-y-1">
              <label htmlFor="lastName" className="block text-sm font-medium text-gray-300">
                Фамилия
              </label>
              <input
                id="lastName"
                type="text"
                autoComplete="family-name"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                className="w-full rounded-lg border border-gray-700 bg-gray-900 px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none transition focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                placeholder="Иванов"
              />
            </div>
          </div>

          <div className="space-y-1">
            <label htmlFor="email" className="block text-sm font-medium text-gray-300">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-gray-700 bg-gray-900 px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none transition focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              placeholder="you@example.com"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="password" className="block text-sm font-medium text-gray-300">
              Пароль
            </label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-gray-700 bg-gray-900 px-4 py-2.5 text-sm text-white placeholder-gray-500 outline-none transition focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              placeholder="••••••••"
            />
            <p className="text-xs text-gray-500">
              Минимум 8 символов, заглавная буква, строчная буква и цифра
            </p>
          </div>

          <button
            type="submit"
            disabled={isPending}
            className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isPending ? 'Регистрация...' : 'Зарегистрироваться'}
          </button>
        </form>

        {/* Footer */}
        <p className="text-center text-sm text-gray-500">
          Уже есть аккаунт?{' '}
          <Link to="/login" className="text-indigo-400 hover:text-indigo-300 transition">
            Войти
          </Link>
        </p>
      </div>
    </div>
  );
}
