import apiClient from './client';

export interface Project {
  id: string;
  name: string;
  status: 'queued' | 'generating' | 'building' | 'ready' | 'failed';
  preview_url: string | null;
  s3_path: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectStatus {
  status: Project['status'];
  preview_url: string | null;
  active_snapshot_version: number | null;
}

export async function listProjects(): Promise<Project[]> {
  const { data } = await apiClient.get<Project[]>('/projects/');
  return data;
}

export async function getProject(id: string): Promise<Project> {
  const { data } = await apiClient.get<Project>(`/projects/${id}`);
  return data;
}

export async function getProjectStatus(id: string): Promise<ProjectStatus> {
  const { data } = await apiClient.get<ProjectStatus>(`/projects/${id}/status`);
  return data;
}

export async function updateProject(id: string, payload: { name?: string }): Promise<Project> {
  const { data } = await apiClient.patch<Project>(`/projects/${id}`, payload);
  return data;
}

export async function deleteProject(id: string): Promise<void> {
  await apiClient.delete(`/projects/${id}`);
}

export async function exportProject(id: string): Promise<Blob> {
  const { data } = await apiClient.get(`/projects/${id}/export`, { responseType: 'blob' });
  return data;
}
