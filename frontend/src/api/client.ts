import type { Finding, FullReport, Page, ScanCreated, ScanDiff, ScanSummary, Severity, UploadResult } from '../types';

export class ApiError extends Error {
  constructor(public code: string, message: string, public requestId?: string, public details?: Record<string, unknown>) { super(message); this.name = 'ApiError'; }
}
export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try { response = await fetch(path, options); } catch { throw new ApiError('NETWORK_ERROR', '无法连接服务，请检查网络与后端状态。'); }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(body?.error?.code ?? `HTTP_${response.status}`, body?.error?.message ?? `请求失败（HTTP ${response.status}）`, body?.error?.request_id, body?.error?.details);
  }
  try { return await response.json() as T; } catch { throw new ApiError('INVALID_RESPONSE', '服务返回了无法解析的响应。'); }
}
function query(values: Record<string, string | number | undefined>) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value !== undefined && value !== '') params.set(key, String(value));
  const result = params.toString();
  return result ? `?${result}` : '';
}
const base = '/api/v1';
export const api = {
  listScans: (filters: { q?: string; status?: string; limit?: number; offset?: number } = {}) => request<Page<ScanSummary>>(`${base}/scans${query(filters)}`),
  scan: (id: string) => request<ScanSummary>(`${base}/scans/${encodeURIComponent(id)}`),
  report: (id: string) => request<FullReport>(`${base}/scans/${encodeURIComponent(id)}/report`),
  findings: (id: string, filters: { severity?: Severity; engine?: string; limit?: number; offset?: number } = {}) => request<Page<Finding>>(`${base}/scans/${encodeURIComponent(id)}/findings${query(filters)}`),
  upload: (file: File, ownerLabel: string) => { const body = new FormData(); body.append('file', file); body.append('owner_label', ownerLabel); return request<UploadResult>(`${base}/skills/upload`, { method: 'POST', body }); },
  createScan: (versionId: string, modes = ['schema', 'static', 'quality'], force = false) => request<ScanCreated>(`${base}/scans`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ version_id: versionId, modes, force }) }),
  compare: (left: string, right: string) => request<ScanDiff>(`${base}/compare${query({ left, right })}`),
};
export async function downloadReport(id: string): Promise<void> {
  const report = await api.report(id);
  const objectUrl = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json;charset=utf-8' }));
  const anchor = document.createElement('a'); anchor.href = objectUrl;
  anchor.download = `sqsp-${id.replace(/[^a-zA-Z0-9_-]/g, '')}.json`;
  document.body.appendChild(anchor); anchor.click(); anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}
