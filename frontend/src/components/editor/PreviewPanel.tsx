import { useEditorStore } from '@/store/editorStore';

export default function PreviewPanel() {
  const { previewUrl, isBuilding } = useEditorStore();

  return (
    <div className="relative flex h-full flex-col">
      <div className="flex items-center border-b border-gray-800 px-3 py-1.5">
        <span className="text-xs text-gray-400">Превью</span>
        {isBuilding && (
          <span className="ml-2 text-xs text-yellow-400">Сборка...</span>
        )}
      </div>
      {previewUrl ? (
        <iframe
          key={previewUrl}
          src={previewUrl}
          sandbox="allow-scripts allow-same-origin"
          className="flex-1 w-full border-0"
          title="preview"
        />
      ) : (
        <div className="flex flex-1 items-center justify-center text-sm text-gray-500">
          {isBuilding ? 'Идёт сборка...' : 'Нет превью'}
        </div>
      )}
    </div>
  );
}
