import { create } from 'zustand';
import type { GenerationStatus } from '@/api/generation';

interface GenerationStore {
  projectId: string | null;
  status: GenerationStatus | null;
  isStreaming: boolean;

  setProjectId: (id: string) => void;
  setStatus: (status: GenerationStatus) => void;
  setIsStreaming: (v: boolean) => void;
  reset: () => void;
}

export const useGenerationStore = create<GenerationStore>((set) => ({
  projectId: null,
  status: null,
  isStreaming: false,

  setProjectId: (id) => set({ projectId: id }),
  setStatus: (status) => set({ status }),
  setIsStreaming: (v) => set({ isStreaming: v }),
  reset: () => set({ projectId: null, status: null, isStreaming: false }),
}));
