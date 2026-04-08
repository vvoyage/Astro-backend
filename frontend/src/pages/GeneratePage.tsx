import { useParams } from 'react-router-dom';
import PromptForm from '@/components/generation/PromptForm';
import ProgressView from '@/components/generation/ProgressView';

export default function GeneratePage() {
  const { projectId } = useParams<{ projectId?: string }>();

  if (projectId) {
    return (
      <div className="flex min-h-full items-start justify-center p-6">
        <div className="w-full max-w-lg">
          <ProgressView projectId={projectId} />
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="mb-6 text-2xl font-bold">Создать новый проект</h1>
      <PromptForm />
    </div>
  );
}
