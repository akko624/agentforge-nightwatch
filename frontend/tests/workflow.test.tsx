import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppRoutes } from '../src/App';
import { diff, finding, otherScan, report, scan } from './fixtures';

function renderApp(path = '/') { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><ConfigProvider locale={zhCN}><MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter></ConfigProvider></QueryClientProvider>); }
function response(data: unknown, status = 200) { return { ok: status < 400, status, json: async () => data } as Response; }
type FetchHandler = (path: string, options?: RequestInit) => Response;
function mockFetch(handler: FetchHandler) { return vi.stubGlobal('fetch', vi.fn(async (path: string, options?: RequestInit) => path === '/healthz' ? response({ status: 'ok' }) : handler(path, options))); }
function defaultHandler(path: string): Response {
  if (path.startsWith('/api/v1/scans?')) return response({ items: [scan, otherScan], total: 2 });
  if (path === '/api/v1/scans/scan-one') return response(scan);
  if (path === '/api/v1/scans/scan-two') return response(otherScan);
  if (path.endsWith('/report')) return response(report);
  if (path.includes('/findings')) return response({ items: [finding], total: 1 });
  if (path.startsWith('/api/v1/compare?')) return response(diff);
  throw new Error(`Unexpected request: ${path}`);
}
beforeEach(() => mockFetch(defaultHandler));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('live-connected pages', () => {
  it('shows health and a truthful empty workspace', async () => {
    mockFetch(() => response({ items: [], total: 0 })); renderApp();
    expect(await screen.findByText('API 在线')).toBeInTheDocument();
    expect(await screen.findByText('暂无扫描，上传第一个 Skill 开始检测。')).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith('/healthz', undefined);
  });
  it('sends search and status filters to the server', async () => {
    renderApp(); await screen.findAllByText('sample-skill');
    const search = screen.getByRole('textbox', { name: '搜索 Skill 名称' });
    fireEvent.change(search, { target: { value: 'report' } }); fireEvent.keyDown(search, { key: 'Enter', code: 'Enter', keyCode: 13 });
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([path]) => String(path).includes('q=report'))).toBe(true));
    fireEvent.mouseDown(screen.getByRole('combobox', { name: '扫描状态筛选' }));
    fireEvent.click(await screen.findByText('FAILED'));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([path]) => String(path).includes('status=FAILED'))).toBe(true));
  });
  it('shows a list API error without inventing results', async () => {
    mockFetch(() => response({ error: { code: 'DB_UNAVAILABLE', message: 'Database unavailable', request_id: 'request-test' } }, 503)); renderApp();
    expect(await screen.findByText('DB_UNAVAILABLE')).toBeInTheDocument();
    expect(screen.getByText('Database unavailable')).toBeInTheDocument();
    expect(screen.queryByText('sample-skill')).not.toBeInTheDocument();
  });
  it('uploads a real FormData file, creates a scan, and displays the queued state', async () => {
    mockFetch((path, options) => {
      if (path === '/api/v1/skills/upload') { expect(options?.body).toBeInstanceOf(FormData); return response({ skill_id: scan.skill_id, version_id: scan.version_id, sha256: scan.artifact_sha256 }, 201); }
      if (path === '/api/v1/scans' && options?.method === 'POST') { expect(JSON.parse(options.body as string)).toEqual({ version_id: scan.version_id, modes: ['schema', 'static', 'quality'], force: false }); return response({ scan_id: scan.scan_id, status: 'QUEUED' }, 202); }
      if (path === '/api/v1/scans/scan-one') return response({ ...scan, status: 'QUEUED', completed_at: null });
      return defaultHandler(path);
    });
    const { container } = renderApp('/upload'); await screen.findByText('导入首个支持的 Agent 工件');
    fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [new File(['synthetic-zip'], 'test.zip', { type: 'application/zip' })] } });
    await waitFor(() => expect(screen.getByRole('button', { name: '上传并创建扫描' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '上传并创建扫描' }));
    expect(await screen.findByText('任务已入队，等待独立 Worker')).toBeInTheDocument();
  });
  it('shows the exact archive rejection and never creates a scan', async () => {
    mockFetch((path) => path === '/api/v1/skills/upload' ? response({ error: { code: 'INVALID_ARCHIVE', message: 'Unsafe archive entry', request_id: 'archive-test' } }, 400) : defaultHandler(path));
    const { container } = renderApp('/upload'); await screen.findByText('导入首个支持的 Agent 工件');
    fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [new File(['bad'], 'attack.zip')] } });
    await waitFor(() => expect(screen.getByRole('button', { name: '上传并创建扫描' })).toBeEnabled()); fireEvent.click(screen.getByRole('button', { name: '上传并创建扫描' }));
    expect(await screen.findByText('INVALID_ARCHIVE')).toBeInTheDocument(); expect(screen.getByText('Unsafe archive entry')).toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.some(([path, options]) => path === '/api/v1/scans' && options?.method === 'POST')).toBe(false);
  });
  it('rejects a non-ZIP selection before contacting upload API', async () => {
    const { container } = renderApp('/upload'); await screen.findByText('导入首个支持的 Agent 工件');
    fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [new File(['x'], 'unsafe.exe')] } });
    expect(await screen.findByText('仅支持 .zip 文件。')).toBeInTheDocument(); expect(screen.getByRole('button', { name: '上传并创建扫描' })).toBeDisabled();
  });
  it('keeps partial coverage, null quality, evidence escaping and finding filters visible', async () => {
    const { container } = renderApp('/scans/scan-one');
    expect(await screen.findByText('部分完成：不能据此判定全面安全')).toBeInTheDocument();
    expect(screen.getByText('完整质量分：未评测（null）')).toBeInTheDocument();
    expect(screen.getByText('Sandbox not configured')).toBeInTheDocument();
    expect(screen.getByText('未运行 · NOT_RUN')).toBeInTheDocument(); expect(screen.getByText('No model configured')).toBeInTheDocument();
    fireEvent.click(await screen.findByText('Reads synthetic credential path'));
    expect(await screen.findByText(finding.evidence_excerpt!)).toBeInTheDocument(); expect(container.querySelector('img[src="x"]')).toBeNull();
    fireEvent.mouseDown(screen.getByRole('combobox', { name: '风险级别筛选' }));
    const highOptions = await screen.findAllByText('HIGH'); fireEvent.click(highOptions[highOptions.length - 1]);
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([path]) => String(path).includes('severity=HIGH'))).toBe(true));
    fireEvent.mouseDown(screen.getByRole('combobox', { name: '检测引擎筛选' }));
    const engineOptions = await screen.findAllByText('builtin-static'); fireEvent.click(engineOptions[engineOptions.length - 1]);
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([path]) => String(path).includes('engine=builtin-static'))).toBe(true));
    fireEvent.click(screen.getByRole('tab', { name: '质量维度与依据' }));
    expect(await screen.findByText('完整质量分未评测，不等于 0 分')).toBeInTheDocument(); expect(within(screen.getByRole('tabpanel', { name: '质量维度与依据' })).getByText('功能正确性')).toBeInTheDocument();
  });
  it('shows a failed scan and leaves report download disabled', async () => {
    mockFetch((path) => path === '/api/v1/scans/scan-one' ? response({ ...scan, status: 'FAILED', error_code: 'ARTIFACT_INTEGRITY_ERROR' }) : defaultHandler(path));
    renderApp('/scans/scan-one'); expect(await screen.findByText('扫描失败，未授予安全结论')).toBeInTheDocument();
    expect(screen.getByText('ARTIFACT_INTEGRITY_ERROR')).toBeInTheDocument(); expect(screen.getByRole('button', { name: '导出 JSON' })).toBeDisabled();
    expect(vi.mocked(fetch).mock.calls.some(([path]) => String(path).endsWith('/report'))).toBe(false);
  });
  it('compares persisted versions and displays resolved and unmeasured differences', async () => {
    renderApp('/compare?left=scan-one&right=scan-two');
    expect(await screen.findByText('New download execution evidence')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '已解决（1）' })); expect(await screen.findByText('Reads synthetic credential path')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '质量维度变化' })); expect(await screen.findByText('未评测值保留为空，不计算虚构提升')).toBeInTheDocument();
    expect(screen.getByText('不适用')).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith('/api/v1/compare?left=scan-one&right=scan-two', undefined);
  });
  it('shows a comparison conflict returned by the backend', async () => {
    mockFetch((path) => path.startsWith('/api/v1/compare?') ? response({ error: { code: 'UNRELATED_SCANS', message: 'Only versions of the same Skill can be compared' } }, 409) : defaultHandler(path));
    renderApp('/compare?left=scan-one&right=scan-two'); expect(await screen.findByText('UNRELATED_SCANS')).toBeInTheDocument();
  });
});
