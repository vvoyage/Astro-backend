import { StrictMode, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import { AuthProvider, userManager } from '@/auth/AuthProvider';
import { ProtectedRoute } from '@/auth/ProtectedRoute';
import LoginPage from '@/pages/LoginPage';
import RegisterPage from '@/pages/RegisterPage';
import DashboardPage from '@/pages/DashboardPage';
import GeneratePage from '@/pages/GeneratePage';
import EditorPage from '@/pages/EditorPage';
import NotFoundPage from '@/pages/NotFoundPage';
import AppLayout from '@/components/layout/AppLayout';
import './index.css';

function AuthCallback() {
  const navigate = useNavigate();
  useEffect(() => {
    userManager
      .signinRedirectCallback()
      .then(() => {
        // Sync is handled by AuthProvider's userLoaded event
        navigate('/dashboard', { replace: true });
      })
      .catch(() => navigate('/login', { replace: true }));
  }, [navigate]);
  return (
    <div className="flex h-screen items-center justify-center text-gray-400">
      Авторизация...
    </div>
  );
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/auth/callback" element={<AuthCallback />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <DashboardPage />
                  </AppLayout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/generate"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <GeneratePage />
                  </AppLayout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/generate/:projectId/progress"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <GeneratePage />
                  </AppLayout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/editor/:projectId"
              element={
                <ProtectedRoute>
                  <EditorPage />
                </ProtectedRoute>
              }
            />
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </BrowserRouter>
        <Toaster theme="dark" position="bottom-right" richColors />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
