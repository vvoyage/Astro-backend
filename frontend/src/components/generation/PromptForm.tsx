import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { listTemplates, startGeneration } from '@/api/generation';
import Button from '@/components/ui/Button';
import TemplateCard from './TemplateCard';

export default function PromptForm() {
  const navigate = useNavigate();
  const [prompt, setPrompt] = useState('');
  const [templateSlug, setTemplateSlug] = useState<string | undefined>();

  const { data: templates } = useQuery({
    queryKey: ['templates'],
    queryFn: listTemplates,
  });

  const generateMut = useMutation({
    mutationFn: () => startGeneration({ prompt, template_slug: templateSlug }),
    onSuccess: ({ project_id }) => navigate(`/generate/${project_id}/progress`),
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail ?? 'Ошибка при запуске генерации');
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        generateMut.mutate();
      }}
      className="flex flex-col gap-6"
    >
      <div>
        <label className="mb-2 block text-sm text-gray-400">Опишите ваш сайт</label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Например: лендинг для фитнес-студии с секциями о нас, расписание и контакты..."
          rows={6}
          className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
          required
        />
      </div>

      {templates && templates.length > 0 && (
        <div>
          <p className="mb-3 text-sm text-gray-400">Или выберите шаблон</p>
          <div className="grid grid-cols-2 gap-3">
            {templates.map((t) => (
              <TemplateCard
                key={t.id}
                template={t}
                selected={templateSlug === t.id}
                onSelect={() => {
                  setTemplateSlug(t.id);
                  if (t.prompt_hint) setPrompt(t.prompt_hint);
                }}
              />
            ))}
          </div>
        </div>
      )}

      <Button type="submit" loading={generateMut.isPending} disabled={!prompt.trim()}>
        Генерировать
      </Button>
    </form>
  );
}
