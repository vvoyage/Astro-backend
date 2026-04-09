import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { deleteProject, exportProject, type Project } from '@/api/projects';
import Button from '@/components/ui/Button';

const statusLabel: Record<Project['status'], string> = {
  queued: 'В очереди',
  generating: 'Генерация...',
  building: 'Сборка...',
  ready: 'Готов',
  failed: 'Ошибка',
};

const statusColor: Record<Project['status'], string> = {
  queued: 'bg-gray-600',
  generating: 'bg-yellow-500',
  building: 'bg-blue-500',
  ready: 'bg-green-600',
  failed: 'bg-red-600',
};

const ACTIVE_STATUSES: Project['status'][] = ['queued', 'generating', 'building'];

export default function ProjectCard({ project }: { project: Project }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const isActive = ACTIVE_STATUSES.includes(project.status);

  const deleteMut = useMutation({
    mutationFn: () => deleteProject(project.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }),
  });

  const handleExport = async () => {
    const blob = await exportProject(project.id);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${project.name}.zip`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 p-4 flex flex-col gap-3 hover:border-gray-700 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-semibold text-white truncate leading-tight">{project.name}</h3>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium text-white ${statusColor[project.status]} ${isActive ? 'animate-pulse' : ''}`}
        >
          {statusLabel[project.status]}
        </span>
      </div>
      <p className="text-xs text-gray-500">
        {new Date(project.created_at).toLocaleDateString('ru-RU')}
      </p>
      {isActive && (
        <div className="h-1 w-full overflow-hidden rounded-full bg-gray-800">
          <div className="h-full animate-[progress_2s_ease-in-out_infinite] rounded-full bg-indigo-600" />
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {project.status === 'generating' || project.status === 'building' ? (
          <Button
            variant="secondary"
            onClick={() => navigate(`/generate/${project.id}/progress`)}
          >
            Смотреть прогресс
          </Button>
        ) : project.status === 'ready' ? (
          <Button onClick={() => navigate(`/editor/${project.id}`)}>Открыть</Button>
        ) : null}
        <Button variant="secondary" onClick={handleExport} disabled={project.status !== 'ready'}>
          Экспорт
        </Button>
        <Button variant="danger" onClick={() => deleteMut.mutate()} loading={deleteMut.isPending}>
          Удалить
        </Button>
      </div>
    </div>
  );
}
