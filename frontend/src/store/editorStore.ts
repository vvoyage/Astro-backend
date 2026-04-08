import { create } from 'zustand';
import { saveFile as saveFileApi, getFile } from '@/api/editor';

interface EditorStore {
  projectId: string | null;
  files: string[];
  currentFile: string | null;
  fileContent: string;
  isDirty: boolean;
  isEditing: boolean;
  isBuilding: boolean;
  previewUrl: string | null;
  activeSnapshotVersion: number | null;

  setProjectId: (id: string) => void;
  setFiles: (files: string[]) => void;
  setCurrentFile: (path: string) => void;
  setFileContent: (content: string) => void;
  setPreviewUrl: (url: string | null) => void;
  setIsEditing: (v: boolean) => void;
  setIsBuilding: (v: boolean) => void;
  setActiveSnapshotVersion: (version: number | null) => void;
  saveFile: () => Promise<void>;
  reloadCurrentFile: () => Promise<void>;
  refreshPreview: (newUrl?: string) => void;
}

export const useEditorStore = create<EditorStore>((set, get) => ({
  projectId: null,
  files: [],
  currentFile: null,
  fileContent: '',
  isDirty: false,
  isEditing: false,
  isBuilding: false,
  previewUrl: null,
  activeSnapshotVersion: null,

  setProjectId: (id) => set({ projectId: id }),
  setFiles: (files) => set({ files }),
  setCurrentFile: (path) => set({ currentFile: path, isDirty: false }),
  setFileContent: (content) => set({ fileContent: content, isDirty: true }),
  setPreviewUrl: (url) => set({ previewUrl: url }),
  setIsEditing: (v) => set({ isEditing: v }),
  setIsBuilding: (v) => set({ isBuilding: v }),
  setActiveSnapshotVersion: (version) => set({ activeSnapshotVersion: version }),

  saveFile: async () => {
    const { projectId, currentFile, fileContent } = get();
    if (!projectId || !currentFile) return;
    await saveFileApi(projectId, currentFile, fileContent);
    set({ isDirty: false });
  },

  reloadCurrentFile: async () => {
    const { projectId, currentFile } = get();
    if (!projectId || !currentFile) return;
    const fc = await getFile(projectId, currentFile);
    set({ fileContent: fc.content, isDirty: false });
  },

  refreshPreview: (newUrl?: string) => {
    const base = (newUrl ?? get().previewUrl ?? '').split('?')[0];
    if (!base) return;
    set({ previewUrl: `${base}?t=${Date.now()}` });
  },
}));
