import type { Project } from '@/api/projects';
import ProjectCard from './ProjectCard';

export default function ProjectList({ projects }: { projects: Project[] }) {
  if (projects.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-gray-700 p-12 text-center text-gray-500">
        Нет проектов. Создайте первый!
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {projects.map((p) => (
        <ProjectCard key={p.id} project={p} />
      ))}
    </div>
  );
}
