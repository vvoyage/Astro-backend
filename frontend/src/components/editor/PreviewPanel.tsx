import { useEffect, useRef } from 'react';
import { useEditorStore } from '@/store/editorStore';

export default function PreviewPanel() {
  const { previewUrl, isBuilding, selectedElement, setSelectedElement } = useEditorStore();
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Принимаем postMessage из iframe
  useEffect(() => {
    const handler = (e: MessageEvent) => {
      if (e.data?.type === 'element-selected') {
        setSelectedElement({
          editable_id: e.data.editable_id,
          file_path: e.data.file_path ?? '',
          element_html: e.data.element_html ?? '',
        });
      } else if (e.data?.type === 'element-deselected') {
        setSelectedElement(null);
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [setSelectedElement]);

  // Отправляем highlight-element в iframe при смене выбранного элемента
  useEffect(() => {
    const win = iframeRef.current?.contentWindow;
    if (!win) return;
    win.postMessage(
      { type: 'highlight-element', editable_id: selectedElement?.editable_id ?? null },
      '*',
    );
  }, [selectedElement]);

  return (
    <div className="relative flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-gray-800 px-3 py-1.5">
        <span className="text-xs text-gray-400">Превью</span>
        {isBuilding && (
          <span className="text-xs text-yellow-400">Сборка...</span>
        )}
        {selectedElement && (
          <span className="ml-auto rounded bg-indigo-900/60 px-1.5 py-0.5 font-mono text-[10px] text-indigo-300">
            #{selectedElement.editable_id.slice(0, 8)}
          </span>
        )}
      </div>
      {previewUrl ? (
        <iframe
          ref={iframeRef}
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
