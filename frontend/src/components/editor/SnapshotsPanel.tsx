import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listSnapshots, restoreSnapshot } from '@/api/snapshots';
import { useEditorStore } from '@/store/editorStore';
import { streamGenerationStatus } from '@/api/generation';
import { userManager } from '@/auth/AuthProvider';
import { toast } from 'sonner';

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function SnapshotsPanel() {
  const { projectId, setIsBuilding, refreshPreview, activeSnapshotVersion, setActiveSnapshotVersion } =
    useEditorStore();
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);

  const { data: snapshots = [], isLoading } = useQuery({
    queryKey: ['snapshots', projectId],
    queryFn: () => listSnapshots(projectId!),
    enabled: !!projectId && expanded,
  });

  // Дедупликация по версии — одна строка на версию (берём первую запись каждой версии)
  const uniqueVersions = snapshots.reduce<typeof snapshots>((acc, snap) => {
    if (!acc.some((s) => s.version === snap.version)) acc.push(snap);
    return acc;
  }, []);

  // Если пользователь явно восстановил версию — показываем её.
  // Иначе — показываем последний (наибольший) снапшот как текущий.
  const currentVersion = activeSnapshotVersion ?? uniqueVersions[0]?.version ?? null;

  const toastId = useRef<string | number | undefined>(undefined);

  const restore = useMutation({
    mutationFn: ({ id }: { id: string }) => restoreSnapshot(id),
    onMutate: () => {
      setIsBuilding(true);
      toastId.current = toast.loading('Восстановление снапшота...');
    },
    onSuccess: async (data) => {
      setActiveSnapshotVersion(data.version);
      qc.invalidateQueries({ queryKey: ['project-status', projectId] });

      const stream = streamGenerationStatus(projectId!, async () => {
        const u = await userManager.getUser();
        return u?.access_token ?? null;
      });

      try {
        for await (const s of stream) {
          if (s.stage === 'done') {
            toast.success('Снапшот восстановлен — превью обновлено', { id: toastId.current });
            refreshPreview(s.preview_url);
            break;
          }
          if (s.stage === 'failed' || s.stage === 'error') {
            toast.error('Ошибка сборки при восстановлении', { id: toastId.current });
            break;
          }
        }
      } finally {
        setIsBuilding(false);
      }
    },
    onError: () => {
      toast.error('Ошибка восстановления', { id: toastId.current });
      setIsBuilding(false);
    },
  });

  return (
    <div className="border-t border-gray-800">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold uppercase tracking-wider text-gray-500 hover:text-gray-300 transition-colors"
      >
        <span>Версии</span>
        <span
          className="transition-transform"
          style={{ display: 'inline-block', transform: expanded ? 'rotate(180deg)' : 'none' }}
        >
          ▼
        </span>
      </button>

      {expanded && (
        <div className="max-h-48 overflow-y-auto px-2 pb-2">
          {isLoading ? (
            <p className="px-2 py-1 text-xs text-gray-600">Загрузка...</p>
          ) : uniqueVersions.length === 0 ? (
            <p className="px-2 py-1 text-xs text-gray-600">Нет снапшотов</p>
          ) : (
            uniqueVersions.map((snap) => {
              const isCurrent = snap.version === currentVersion;
              return (
                <div
                  key={snap.version}
                  className={`flex items-center justify-between gap-2 rounded px-2 py-1.5 ${
                    isCurrent ? 'bg-indigo-950 ring-1 ring-indigo-700' : 'hover:bg-gray-800'
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <p className="text-xs text-gray-300 truncate">
                        v{snap.version}
                        {snap.description ? ` — ${snap.description}` : ''}
                      </p>
                      {isCurrent && (
                        <span className="shrink-0 rounded bg-indigo-600 px-1 py-0.5 text-[10px] font-semibold text-white leading-none">
                          Текущий
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-600">{formatDate(snap.created_at)}</p>
                  </div>
                  {!isCurrent && (
                    <button
                      onClick={() => restore.mutate({ id: snap.id })}
                      disabled={restore.isPending}
                      className="shrink-0 rounded px-2 py-0.5 text-xs bg-gray-700 text-gray-300 hover:bg-indigo-600 hover:text-white disabled:opacity-50 transition-colors"
                    >
                      Восстановить
                    </button>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
