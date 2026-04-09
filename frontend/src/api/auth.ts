import apiClient from './client';

export interface RegisterRequest {
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
}

export interface RegisterResponse {
  id: string;
  email: string;
  full_name: string | null;
  message: string;
}

export async function registerUser(data: RegisterRequest): Promise<RegisterResponse> {
  const { data: res } = await apiClient.post<RegisterResponse>('/auth/register', data);
  return res;
}

export interface UserResponse {
  id: string;
  keycloak_id: string;
  email: string;
  full_name: string | null;
  created_at: string;
}

/** Matches backend POST /auth/sync response */
export interface SyncResponse {
  id: string;
  email: string;
  full_name: string | null;
  created: boolean;
}

export async function syncUser(): Promise<SyncResponse> {
  const { data } = await apiClient.post<SyncResponse>('/auth/sync');
  return data;
}

export async function getMe(): Promise<UserResponse> {
  const { data } = await apiClient.get<UserResponse>('/users/me');
  return data;
}

export async function updateMe(payload: { full_name?: string }): Promise<UserResponse> {
  const { data } = await apiClient.patch<UserResponse>('/users/me', payload);
  return data;
}
