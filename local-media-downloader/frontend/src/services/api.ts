import type {
  AnalyzeResponse,
  AppSettings,
  CreateDownloadRequest,
  DownloadJobOut,
  HealthResponse,
  HistoryRecordOut,
  UpdateSettingsRequest,
  ValidateFolderResponse,
} from "../types/api";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export class ApiError extends Error {
  technical?: string | null;
  status: number;

  constructor(message: string, status: number, technical?: string | null) {
    super(message);
    this.status = status;
    this.technical = technical;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    });
  } catch {
    throw new ApiError("Could not reach the local backend. Is it running?", 0);
  }

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    let technical: string | undefined;
    try {
      const body = await response.json();
      message = body.message || message;
      technical = body.technical;
    } catch {
      // ignore parse errors, use default message
    }
    throw new ApiError(message, response.status, technical);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),

  analyze: (url: string) =>
    request<AnalyzeResponse>("/api/analyze", { method: "POST", body: JSON.stringify({ url }) }),

  createDownload: (payload: CreateDownloadRequest) =>
    request<DownloadJobOut>("/api/downloads", { method: "POST", body: JSON.stringify(payload) }),

  listDownloads: () => request<DownloadJobOut[]>("/api/downloads"),

  cancelDownload: (id: string) => request<DownloadJobOut>(`/api/downloads/${id}/cancel`, { method: "POST" }),

  retryDownload: (id: string) => request<DownloadJobOut>(`/api/downloads/${id}/retry`, { method: "POST" }),

  listHistory: (params: { search?: string; platform?: string; status?: string; order?: string }) => {
    const query = new URLSearchParams();
    if (params.search) query.set("search", params.search);
    if (params.platform) query.set("platform", params.platform);
    if (params.status) query.set("status", params.status);
    if (params.order) query.set("order", params.order);
    const qs = query.toString();
    return request<HistoryRecordOut[]>(`/api/history${qs ? `?${qs}` : ""}`);
  },

  deleteHistoryRecord: (id: string, deleteFile: boolean) =>
    request<void>(`/api/history/${id}?delete_file=${deleteFile}`, { method: "DELETE" }),

  clearHistory: (deleteFiles: boolean) =>
    request<void>("/api/history/clear", { method: "POST", body: JSON.stringify({ delete_files: deleteFiles }) }),

  getSettings: () => request<AppSettings>("/api/settings"),

  updateSettings: (patch: UpdateSettingsRequest) =>
    request<AppSettings>("/api/settings", { method: "PUT", body: JSON.stringify(patch) }),

  openPath: (path: string) => request<void>("/api/fs/open", { method: "POST", body: JSON.stringify({ path }) }),

  openContainingFolder: (path: string) =>
    request<void>("/api/fs/open-folder", { method: "POST", body: JSON.stringify({ path }) }),

  validateFolder: (path: string) =>
    request<ValidateFolderResponse>("/api/fs/validate-folder", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),
};

export const PROGRESS_STREAM_URL = `${API_BASE}/api/progress/stream`;
