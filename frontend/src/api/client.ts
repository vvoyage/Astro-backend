import axios from 'axios';

let getAccessTokenFn: (() => Promise<string | null>) | null = null;
let silentRefreshFn: (() => Promise<string | null>) | null = null;

export function setTokenProvider(fn: () => Promise<string | null>) {
  getAccessTokenFn = fn;
}

export function setSilentRefreshProvider(fn: () => Promise<string | null>) {
  silentRefreshFn = fn;
}

const apiClient = axios.create({
  baseURL: '/api/v1',
});

apiClient.interceptors.request.use(async (config) => {
  if (getAccessTokenFn) {
    const token = await getAccessTokenFn();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && error.config && silentRefreshFn && !error.config._retry) {
      error.config._retry = true;
      try {
        const token = await silentRefreshFn();
        if (token) {
          error.config.headers.Authorization = `Bearer ${token}`;
          return apiClient.request(error.config);
        }
      } catch {
        // Refresh failed — redirect to login
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);

export default apiClient;
