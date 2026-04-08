import apiClient from './client';

export interface FileContent {
  path: string;
  content: string;
}

export interface AIEditRequest {
  project_id: string;
  element: {
    editable_id: string;
    file_path: string;
    element_html: string;
  };
  instruction: string;
  ai_model?: string;
}

export interface AIEditResponse {
  task_id: string;
}

export async function listFiles(projectId: string): Promise<string[]> {
  const { data } = await apiClient.get<{ project_id: string; files: string[] }>('/editor/files', {
    params: { project_id: projectId },
  });
  return data.files;
}

export async function getFile(projectId: string, path: string): Promise<FileContent> {
  const { data } = await apiClient.get<{ project_id: string; file_path: string; content: string }>('/editor/file', {
    params: { project_id: projectId, file_path: path },
  });
  return { path: data.file_path, content: data.content };
}

export async function saveFile(projectId: string, path: string, content: string): Promise<void> {
  await apiClient.put('/editor/file', { project_id: projectId, file_path: path, content });
}

export async function submitAIEdit(payload: AIEditRequest): Promise<AIEditResponse> {
  const { data } = await apiClient.post<AIEditResponse>('/editor/edit', payload);
  return data;
}

export async function triggerRebuild(projectId: string): Promise<void> {
  await apiClient.post('/editor/rebuild', null, { params: { project_id: projectId } });
}
