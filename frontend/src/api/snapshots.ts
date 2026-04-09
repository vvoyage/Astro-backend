import apiClient from './client';

export interface Snapshot {
  id: string;
  project_id: string;
  version: number;
  description: string | null;
  created_at: string;
}

export async function listSnapshots(projectId: string): Promise<Snapshot[]> {
  const { data } = await apiClient.get<Snapshot[]>(`/snapshots/${projectId}`);
  return data;
}

export interface RestoreResponse {
  snapshot_id: string;
  project_id: string;
  file_path: string;
  version: number;
  status: string;
}

export async function restoreSnapshot(snapshotId: string): Promise<RestoreResponse> {
  const { data } = await apiClient.post<RestoreResponse>(`/snapshots/${snapshotId}/restore`);
  return data;
}
