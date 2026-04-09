import { useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { userManager } from '@/auth/AuthProvider';
import { streamGenerationStatus, type GenerationStatus } from '@/api/generation';
import { useGenerationStore } from '@/store/generationStore';
import ProgressBar from './ProgressBar';
import Button from '@/components/ui/Button';

const STAGES: GenerationStatus['stage'][] = [
  'queued',
  'optimizer',
  'architect',
  'code_generator',
  'saving',
  'building',
  'done',
];

const stageLabels: Record<GenerationStatus['stage'], string> = {
  queued: 'В очереди...',
  optimizer: 'Оптимизация промпта',
  architect: 'Проектирование структуры',
  code_generator: 'Генерация кода',
  saving: 'Сохранение файлов',
  building: 'Сборка проекта',
  done: 'Готово!',
  failed: 'Ошибка',
  error: 'Ошибка',
};

export default function ProgressView({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const { status, setStatus, setIsStreaming } = useGenerationStore();

  useEffect(() => {
    let cancelled = false;
    setIsStreaming(true);

    (async () => {
      try {
        const stream = streamGenerationStatus(projectId, async () => {
          const u = await userManager.getUser();
          return u?.access_token ?? null;
        });
        for await (const s of stream) {
          if (cancelled) break;
          setStatus(s);
          if (s.stage === 'done' || s.stage === 'failed' || s.stage === 'error') break;
        }
      } finally {
        if (!cancelled) setIsStreaming(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [projectId, setStatus, setIsStreaming]);

  const currentStageIdx = status ? STAGES.indexOf(status.stage) : 0;
  const isDone = status?.stage === 'done';
  const isFailed = status?.stage === 'failed' || status?.stage === 'error';

  return (
    <div className="mx-auto max-w-lg p-6">
      <h2 className="mb-6 text-xl font-bold">Генерация проекта</h2>
      <ProgressBar progress={status?.progress ?? 0} />

      <p className="mt-4 text-center text-sm text-gray-400">
        {stageLabels[status?.stage ?? 'queued']}
        {status?.message && (
          <span className="block mt-1 text-xs text-gray-500">{status.message}</span>
        )}
      </p>

      <ol className="mt-6 space-y-2">
        {STAGES.filter((s) => s !== 'failed').map((stage, idx) => {
          const done = currentStageIdx > idx || isDone;
          const active = currentStageIdx === idx && !isDone && !isFailed;
          return (
            <li key={stage} className="flex items-center gap-3 text-sm">
              <span
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                  done
                    ? 'bg-green-600 text-white'
                    : active
                      ? 'bg-indigo-600 text-white animate-pulse'
                      : 'bg-gray-800 text-gray-500'
                }`}
              >
                {done ? '✓' : idx + 1}
              </span>
              <span className={done ? 'text-gray-300' : active ? 'text-white' : 'text-gray-600'}>
                {stageLabels[stage]}
              </span>
            </li>
          );
        })}
      </ol>

      {isDone && (
        <div className="mt-8 flex flex-col gap-3">
          <Button className="w-full" onClick={() => navigate(`/editor/${projectId}`)}>
            Открыть редактор
          </Button>
          <Link
            to="/dashboard"
            className="block text-center text-sm text-gray-400 hover:text-white transition-colors"
          >
            ← На дашборд
          </Link>
        </div>
      )}

      {isFailed && (
        <div className="mt-8 flex flex-col gap-3">
          <p className="text-center text-sm text-red-400">
            Что-то пошло не так. Попробуйте создать проект заново.
          </p>
          <Link
            to="/generate"
            className="block text-center text-sm text-indigo-400 hover:text-indigo-300 transition-colors"
          >
            Попробовать снова
          </Link>
        </div>
      )}
    </div>
  );
}
