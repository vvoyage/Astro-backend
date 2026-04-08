import { useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { listFiles, getFile } from '@/api/editor';
import { getProject, getProjectStatus } from '@/api/projects';
import { useEditorStore } from '@/store/editorStore';
import AppLayout from '@/components/layout/AppLayout';
import FileTree from '@/components/editor/FileTree';
import CodePanel from '@/components/editor/CodePanel';
import PreviewPanel from '@/components/editor/PreviewPanel';
import AIEditPanel from '@/components/editor/AIEditPanel';
import SnapshotsPanel from '@/components/editor/SnapshotsPanel';

export default function EditorPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { setProjectId, setFiles, setCurrentFile, setFileContent, setPreviewUrl, setActiveSnapshotVersion, currentFile } =
    useEditorStore();

  useEffect(() => {
    if (projectId) setProjectId(projectId);
    return () => {
      setFiles([]);
      setCurrentFile('');
      setFileContent('');
      setActiveSnapshotVersion(null);
    };
  }, [projectId, setProjectId, setFiles, setCurrentFile, setFileContent, setActiveSnapshotVersion]);

  const { data: project } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => getProject(projectId!),
    enabled: !!projectId,
  });

  useQuery({
    queryKey: ['editor-files', projectId],
    queryFn: async () => {
      const files = await listFiles(projectId!);
      setFiles(files);
      if (files.length > 0 && !currentFile) {
        const first = files[0];
        setCurrentFile(first);
        try {
          const fc = await getFile(projectId!, first);
          setFileContent(fc.content);
        } catch {
          // файл пустой или недоступен — редактор просто останется пустым
        }
      }
      return files;
    },
    enabled: !!projectId,
  });

  useQuery({
    queryKey: ['project-status', projectId],
    queryFn: async () => {
      const s = await getProjectStatus(projectId!);
      if (s.preview_url) setPreviewUrl(s.preview_url);
      // Синхронизируем активную версию из БД — актуально при перезагрузке страницы
      if (s.active_snapshot_version !== undefined) {
        setActiveSnapshotVersion(s.active_snapshot_version ?? null);
      }
      return s;
    },
    enabled: !!projectId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 3000;
      return data.status === 'ready' ? false : 3000;
    },
  });

  return (
    <AppLayout>
      <div className="flex h-full min-h-0 flex-col">
        {/* Top bar */}
        <div className="flex shrink-0 items-center gap-3 border-b border-gray-800 px-4 py-2">
          <Link to="/" className="text-xs text-gray-500 hover:text-gray-300 transition-colors">
            ← Проекты
          </Link>
          {project && (
            <>
              <span className="text-gray-700">/</span>
              <span className="text-sm font-medium text-gray-200">{project.name}</span>
              <span
                className={`ml-1 rounded px-1.5 py-0.5 text-xs font-medium ${
                  project.status === 'ready'
                    ? 'bg-green-900/50 text-green-400'
                    : project.status === 'failed'
                    ? 'bg-red-900/50 text-red-400'
                    : 'bg-yellow-900/50 text-yellow-400'
                }`}
              >
                {project.status}
              </span>
            </>
          )}
        </div>

        {/* Main 3-panel layout */}
        <div className="flex min-h-0 flex-1">
          {/* Left sidebar: file tree + snapshots */}
          <aside className="flex w-56 shrink-0 flex-col border-r border-gray-800">
            <div className="min-h-0 flex-1">
              <FileTree />
            </div>
            <SnapshotsPanel />
          </aside>

          {/* Center: code editor + AI edit panel */}
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="min-h-0 flex-1">
              <CodePanel />
            </div>
            <div className="h-52 shrink-0 border-t border-gray-800">
              <AIEditPanel />
            </div>
          </div>

          {/* Right: preview */}
          <div className="w-[45%] shrink-0 border-l border-gray-800">
            <PreviewPanel />
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
