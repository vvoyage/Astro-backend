import apiClient from './client';

export interface Template {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  is_active: boolean;
  text_prompt: string;
  prompt_hint: string;
  preview_url: string | null;
}

export interface GenerationRequest {
  prompt: string;
  template_slug?: string;
  ai_model?: string;
}

export interface GenerationResponse {
  project_id: string;
  status: string;
}

export interface GenerationStatus {
  stage: 'queued' | 'optimizer' | 'architect' | 'code_generator' | 'saving' | 'building' | 'done' | 'failed' | 'error';
  progress: number;
  message?: string;
  preview_url?: string;
}

const SSE_TERMINAL_STAGES = new Set(['done', 'failed', 'error']);
const SSE_MAX_RETRIES = 5;
const SSE_RETRY_BASE_MS = 1000;

export async function listTemplates(): Promise<Template[]> {
  const { data } = await apiClient.get<Template[]>('/templates/');
  return data;
}

export async function startGeneration(payload: GenerationRequest): Promise<GenerationResponse> {
  const { data } = await apiClient.post<GenerationResponse>('/generation', payload);
  return data;
}

async function* readSSEStream(
  url: string,
  headers: Record<string, string>,
): AsyncGenerator<GenerationStatus> {
  const response = await fetch(url, { headers });

  if (!response.ok) {
    throw new Error(`SSE request failed: ${response.status} ${response.statusText}`);
  }

  if (!response.body) throw new Error('No response body');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split('\n\n');
      buffer = chunks.pop()!;
      for (const chunk of chunks) {
        const line = chunk.trim();
        if (line.startsWith('data: ')) {
          yield JSON.parse(line.slice(6)) as GenerationStatus;
        }
      }
    }
  } finally {
    reader.cancel().catch(() => undefined);
  }
}

export async function* streamGenerationStatus(
  projectId: string,
  getToken: () => Promise<string | null>,
): AsyncGenerator<GenerationStatus> {
  const url = `/api/v1/generation/${projectId}/status`;
  let retries = 0;

  while (retries <= SSE_MAX_RETRIES) {
    const token = await getToken();
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

    try {
      for await (const status of readSSEStream(url, headers)) {
        yield status;
        if (SSE_TERMINAL_STAGES.has(status.stage)) return;
      }
      // Stream ended without terminal stage — treat as done if we've gone this far
      return;
    } catch (err) {
      retries++;
      if (retries > SSE_MAX_RETRIES) throw err;
      // Exponential backoff before retry
      await new Promise((resolve) =>
        setTimeout(resolve, SSE_RETRY_BASE_MS * Math.pow(2, retries - 1)),
      );
    }
  }
}
