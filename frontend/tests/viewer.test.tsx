import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppRoutes } from '../src/App';
import { report, scan } from './fixtures';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function openViewer() {
  const fetch = vi.fn(() => { throw new Error('Viewer must not contact API'); }); vi.stubGlobal('fetch', fetch);
  const result = render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={['/viewer']}><AppRoutes /></MemoryRouter></QueryClientProvider>);
  return { ...result, fetch };
}
function fileOf(value: unknown) {
  const text = JSON.stringify(value); const file = new File([text], 'report.json', { type: 'application/json' });
  Object.defineProperty(file, 'text', { value: async () => text }); return file;
}

describe('browser-only report viewer', () => {
  it('loads a local report without API calls or browser persistence and clears it', async () => {
    const { container, fetch } = openViewer();
    await screen.findByText('本地查看，无需上传报告');
    expect(fetch).not.toHaveBeenCalled();
    const source = { ...structuredClone(report), engines: Object.entries(scan.stages).map(([name, result]) => ({ name, version: '1.0', ...result })) };
    fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [fileOf(source)] } });
    expect(await screen.findByText('用户提供的报告，未经平台验签')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: '验证报告核心看板' })).toBeInTheDocument();
    expect(screen.getByText('sample-skill')).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0);
    fireEvent.click(screen.getByRole('button', { name: '清除当前报告' }));
    await waitFor(() => expect(screen.queryByText('sample-skill')).not.toBeInTheDocument());
  });
  it('rejects invalid input without retaining a misleading report', async () => {
    const { container, fetch } = openViewer(); await screen.findByText('本地查看，无需上传报告');
    fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [fileOf({ schema_version: 'unsupported' })] } });
    expect(await screen.findByText(/UNSUPPORTED_REPORT/)).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '验证报告核心看板' })).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
});
