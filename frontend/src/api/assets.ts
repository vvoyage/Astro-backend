import apiClient from './client';

export interface Asset {
  id: string;
  project_id: string;
  filename: string;
  url: string;
  created_at: string;
}

export async function listAssets(projectId: string): Promise<Asset[]> {
  const { data } = await apiClient.get<Asset[]>('/assets/', {
    params: { project_id: projectId },
  });
  return data;
}

export async function uploadAsset(projectId: string, file: File): Promise<Asset> {
  const form = new FormData();
  form.append('file', file);
  form.append('project_id', projectId);
  const { data } = await apiClient.post<Asset>('/assets/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function deleteAsset(assetId: string): Promise<void> {
  await apiClient.delete(`/assets/${assetId}`);
}
