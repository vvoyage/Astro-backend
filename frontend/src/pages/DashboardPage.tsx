import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { listProjects } from '@/api/projects';
import ProjectList from '@/components/projects/ProjectList';

function ProjectSkeletons() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="rounded-xl border border-gray-800 bg-gray-900 p-4 flex flex-col gap-3 animate-pulse">
          <div className="flex items-center justify-between gap-2">
            <div className="h-4 w-40 rounded bg-gray-800" />
            <div className="h-5 w-16 rounded-full bg-gray-800" />
          </div>
          <div className="h-3 w-24 rounded bg-gray-800" />
          <div className="flex gap-2">
            <div className="h-8 w-20 rounded-lg bg-gray-800" />
            <div className="h-8 w-20 rounded-lg bg-gray-800" />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const { data: projects, isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: listProjects,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      const hasActive = data.some(
        (p) => p.status === 'queued' || p.status === 'generating' || p.status === 'building',
      );
      return hasActive ? 5000 : false;
    },
  });

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Мои проекты</h1>
        <Link
          to="/generate"
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
        >
          + Новый проект
        </Link>
      </div>
      {isLoading ? <ProjectSkeletons /> : <ProjectList projects={projects ?? []} />}
    </div>
  );
}
