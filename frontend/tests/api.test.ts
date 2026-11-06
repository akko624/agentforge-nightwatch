import { afterEach, expect, it, vi } from 'vitest';
import { api, ApiError, downloadReport, request } from '../src/api/client';
import { report } from './fixtures';

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers(); });
it('encodes scan IDs and filters into the requested API URL', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [], total: 0 }) }));
  await api.findings('../unsafe', { severity: 'HIGH', engine: 'engine & test', offset: 20 });
  expect(fetch).toHaveBeenCalledWith('/api/v1/scans/..%2Funsafe/findings?severity=HIGH&engine=engine+%26+test&offset=20', undefined);
});
it('preserves structured error code and request ID', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 400, json: async () => ({ error: { code: 'INVALID_ARCHIVE', message: 'Unsafe archive', request_id: 'req-id', details: { path: '..' } } }) }));
  await expect(request('/test')).rejects.toMatchObject({ code: 'INVALID_ARCHIVE', requestId: 'req-id', details: { path: '..' } });
});
it('handles offline and invalid responses explicitly', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline'))); await expect(request('/test')).rejects.toBeInstanceOf(ApiError);
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => { throw new Error('not json'); } })); await expect(request('/test')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
});
it('downloads the fetched JSON report with a fixed safe filename and revokes its URL', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => report }));
  const create = vi.fn(() => 'blob:report'); const revoke = vi.fn();
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: create }); Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revoke });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { expect(this.download).toBe('sqsp-scan-one.json'); expect(this.href).toBe('blob:report'); });
  await downloadReport('scan-one'); expect(fetch).toHaveBeenCalledWith('/api/v1/scans/scan-one/report', undefined); expect(create).toHaveBeenCalledWith(expect.any(Blob)); expect(click).toHaveBeenCalledOnce();
  vi.runAllTimers(); expect(revoke).toHaveBeenCalledWith('blob:report');
});
