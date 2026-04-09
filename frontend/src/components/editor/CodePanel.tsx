import { useState } from 'react';
import Editor from '@monaco-editor/react';
import { useQueryClient } from '@tanstack/react-query';
import { useEditorStore } from '@/store/editorStore';
import { triggerRebuild } from '@/api/editor';
import { streamGenerationStatus } from '@/api/generation';
import { userManager } from '@/auth/AuthProvider';
import Button from '@/components/ui/Button';
import { toast } from 'sonner';

function detectLanguage(path: string | null): string {
  if (!path) return 'plaintext';
  const ext = path.split('.').pop() ?? '';
  const map: Record<string, string> = {
    ts: 'typescript',
    tsx: 'typescript',
    js: 'javascript',
    jsx: 'javascript',
    css: 'css',
    scss: 'scss',
    json: 'json',
    md: 'markdown',
    html: 'html',
    astro: 'html',
  };
  return map[ext] ?? 'plaintext';
}

export default function CodePanel() {
  const { projectId, currentFile, fileContent, isDirty, setFileContent, saveFile, setIsBuilding, refreshPreview, setActiveSnapshotVersion } =
    useEditorStore();
  const qc = useQueryClient();
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async () => {
    if (!projectId) return;
    setIsSaving(true);
    try {
      await saveFile();
      setActiveSnapshotVersion(null);
      qc.invalidateQueries({ queryKey: ['snapshots', projectId] });
      const toastId = toast.loading('Файл сохранён, запускаем сборку...');

      setIsBuilding(true);
      await triggerRebuild(projectId);

      const stream = streamGenerationStatus(projectId, async () => {
        const u = await userManager.getUser();
        return u?.access_token ?? null;
      });

      for await (const s of stream) {
        if (s.stage === 'done') {
          toast.success('Сборка завершена — превью обновлено', { id: toastId });
          refreshPreview(s.preview_url);
          break;
        }
        if (s.stage === 'failed' || s.stage === 'error') {
          toast.error('Ошибка сборки', { id: toastId });
          break;
        }
      }
    } catch {
      toast.error('Не удалось сохранить файл');
    } finally {
      setIsSaving(false);
      setIsBuilding(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-gray-800 px-3 py-1.5">
        <span className="text-xs text-gray-400">{currentFile ?? 'Выберите файл'}</span>
        <Button
          onClick={handleSave}
          disabled={!isDirty || !currentFile || isSaving}
          variant="secondary"
          className="py-1 text-xs"
        >
          {isSaving ? 'Сборка...' : 'Сохранить'}
        </Button>
      </div>
      <div className="flex-1">
        <Editor
          height="100%"
          language={detectLanguage(currentFile)}
          value={fileContent}
          onChange={(v) => setFileContent(v ?? '')}
          theme="vs-dark"
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            wordWrap: 'on',
          }}
        />
      </div>
    </div>
  );
}
