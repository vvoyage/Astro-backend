import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { submitAIEdit } from '@/api/editor';
import { useEditorStore } from '@/store/editorStore';
import { userManager } from '@/auth/AuthProvider';
import { streamGenerationStatus } from '@/api/generation';
import { toast } from 'sonner';
import Button from '@/components/ui/Button';

export default function AIEditPanel() {
  const [prompt, setPrompt] = useState('');
  const { projectId, currentFile, files, setIsEditing, setIsBuilding, refreshPreview, reloadCurrentFile, setActiveSnapshotVersion, selectedElement } =
    useEditorStore();
  const qc = useQueryClient();

  const [selectedFile, setSelectedFile] = useState<string>('');

  // Автовыбор файла при клике на элемент в превью
  useEffect(() => {
    if (selectedElement?.file_path) {
      setSelectedFile(selectedElement.file_path);
    }
  }, [selectedElement]);

  const targetFile = selectedFile || currentFile || '';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || !prompt.trim()) return;

    const target = targetFile || '*';
    setIsEditing(true);
    const toastId = toast.loading(target === '*' ? 'AI редактирует весь проект...' : 'AI редактирует файл...');
    try {
      await submitAIEdit({
        project_id: projectId,
        element: { editable_id: selectedElement?.editable_id ?? '', file_path: target, element_html: selectedElement?.element_html ?? '' },
        instruction: prompt,
      });

      setIsBuilding(true);
      const stream = streamGenerationStatus(projectId, async () => {
        const u = await userManager.getUser();
        return u?.access_token ?? null;
      });
      for await (const s of stream) {
        if (s.stage === 'done') {
          toast.success('AI редактирование применено', { id: toastId });
          setActiveSnapshotVersion(null);
          qc.invalidateQueries({ queryKey: ['snapshots', projectId] });
          await reloadCurrentFile();
          refreshPreview(s.preview_url);
          break;
        }
        if (s.stage === 'failed' || s.stage === 'error') {
          toast.error('Ошибка редактирования', { id: toastId });
          break;
        }
      }
    } catch {
      toast.error('Не удалось применить редактирование', { id: toastId });
    } finally {
      setIsEditing(false);
      setIsBuilding(false);
      setPrompt('');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex h-full flex-col gap-2 p-3">
      <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">AI-редактор</p>
      <div className="flex gap-2">
        <select
          value={targetFile}
          onChange={(e) => setSelectedFile(e.target.value)}
          className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-xs text-gray-300 focus:outline-none"
        >
          <option value="*">Весь проект</option>
          <option value="">Текущий файл</option>
          {files.map((f) => (
            <option key={f} value={f}>{f}</option>
          ))}
        </select>
      </div>
      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="Что изменить? Например: сделай заголовок синим"
        rows={2}
        className="flex-1 rounded border border-gray-700 bg-gray-900 px-2 py-1.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none resize-none"
      />
      <p className="text-[11px] text-gray-500">
        {selectedElement
          ? <>
              Элемент: <span className="font-mono text-indigo-400">#{selectedElement.editable_id.slice(0, 8)}</span>
              {selectedElement.file_path && (
                <span className="ml-1 text-gray-600">({selectedElement.file_path})</span>
              )}
            </>
          : 'Кликните на элемент в превью'}
      </p>
      <Button type="submit" disabled={!prompt.trim() || (selectedFile === '' && !currentFile)}>
        Применить через AI
      </Button>
    </form>
  );
}
