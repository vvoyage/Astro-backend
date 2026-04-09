import { useState } from 'react';
import { useEditorStore } from '@/store/editorStore';
import { getFile } from '@/api/editor';
import { toast } from 'sonner';

interface TreeNode {
  name: string;
  path: string;
  children: TreeNode[];
  isFile: boolean;
}

function buildTree(files: string[]): TreeNode[] {
  const root: TreeNode[] = [];

  for (const file of files) {
    const parts = file.split('/');
    let nodes = root;
    let pathSoFar = '';

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      pathSoFar = pathSoFar ? `${pathSoFar}/${part}` : part;
      const isFile = i === parts.length - 1;
      let node = nodes.find((n) => n.name === part);
      if (!node) {
        node = { name: part, path: pathSoFar, children: [], isFile };
        nodes.push(node);
      }
      nodes = node.children;
    }
  }

  return root;
}

function FolderIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="14" height="14" viewBox="0 0 16 16" fill="none"
      className="shrink-0 transition-transform"
      style={{ transform: open ? 'rotate(90deg)' : 'none' }}
    >
      <path d="M6 3H2a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1H8L6 3Z" fill="#8b949e" />
    </svg>
  );
}

function FileIcon({ name }: { name: string }) {
  const ext = name.split('.').pop() ?? '';

  if (ext === 'astro') {
    return (
      <img src="/icons/astro.svg" width={12} height={14} alt="astro" className="shrink-0 brightness-[4]" />
    );
  }
  if (ext === 'html') {
    return (
      <img src="/icons/html5.svg" width={12} height={14} alt="html" className="shrink-0" />
    );
  }

  const colors: Record<string, string> = {
    ts: '#3178c6', tsx: '#3178c6',
    js: '#f7df1e', jsx: '#f7df1e',
    css: '#264de4', scss: '#c76494',
    json: '#cbcb41',
    md: '#adbac7',
  };
  const color = colors[ext] ?? '#8b949e';

  return (
    <svg width="12" height="14" viewBox="0 0 12 14" fill="none" className="shrink-0">
      <path d="M1 1h7l3 3v9H1V1Z" fill={color} fillOpacity={0.15} stroke={color} strokeWidth="1" />
      <path d="M8 1v3h3" stroke={color} strokeWidth="1" fill="none" />
    </svg>
  );
}

function TreeNodeItem({ node, depth = 0 }: { node: TreeNode; depth?: number }) {
  const { currentFile, setCurrentFile, setFileContent, projectId } = useEditorStore();
  const [open, setOpen] = useState(depth === 0);

  const handleClick = async () => {
    if (!node.isFile) {
      setOpen((v) => !v);
      return;
    }
    if (!projectId) return;
    setCurrentFile(node.path);
    try {
      const fc = await getFile(projectId, node.path);
      setFileContent(fc.content);
    } catch {
      toast.error(`Не удалось загрузить файл: ${node.name}`);
    }
  };

  const isActive = currentFile === node.path;

  return (
    <div>
      <button
        onClick={handleClick}
        className={`flex w-full items-center gap-1.5 rounded py-1 text-left text-sm transition-colors ${
          isActive
            ? 'bg-indigo-600/30 text-white'
            : 'text-gray-400 hover:bg-gray-800 hover:text-white'
        }`}
        style={{ paddingLeft: `${8 + depth * 12}px`, paddingRight: '8px' }}
      >
        {node.isFile ? (
          <FileIcon name={node.name} />
        ) : (
          <FolderIcon open={open} />
        )}
        <span className="truncate">{node.name}</span>
      </button>
      {!node.isFile && open && node.children.map((child) => (
        <TreeNodeItem key={child.path} node={child} depth={depth + 1} />
      ))}
    </div>
  );
}

export default function FileTree() {
  const { files } = useEditorStore();
  const tree = buildTree(files);

  return (
    <div className="h-full overflow-y-auto p-2">
      <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-gray-500">Файлы</p>
      {files.length === 0 ? (
        <p className="px-2 text-xs text-gray-600">Нет файлов</p>
      ) : (
        tree.map((node) => (
          <TreeNodeItem key={node.path} node={node} />
        ))
      )}
    </div>
  );
}
