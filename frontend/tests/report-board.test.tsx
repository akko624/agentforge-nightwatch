import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ReportBoard } from '../src/components/report/ReportBoard';
import { finding, report, scan } from './fixtures';
import type { FullReport } from '../src/types';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('evidence-driven report board', () => {
  it('shows quality coverage as measured weights and preserves null full quality', () => {
    render(<ReportBoard report={report} scan={scan} />);
    expect(screen.getByRole('region', { name: '验证报告核心看板' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: '质量评测覆盖 40%，其余 60% 未完成' })).toBeInTheDocument();
    expect(screen.getByText('完整质量分：未评测（null）')).toBeInTheDocument();
    expect(screen.getAllByText('未运行 · 不赋予分数')).toHaveLength(2);
    expect(screen.getByText('结构与说明的启发式，不代表任务成功率')).toBeInTheDocument();
  });

  it('uses complete-report counts and sends a severity selection without requests', () => {
    const onSelect = vi.fn();
    const fetchSpy = vi.fn(); vi.stubGlobal('fetch', fetchSpy);
    render(<ReportBoard report={report} scan={scan} onSeveritySelect={onSelect} />);
    fireEvent.click(screen.getByRole('button', { name: '按 HIGH 筛选（1 条）' }));
    expect(onSelect).toHaveBeenCalledExactlyOnceWith('HIGH');
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(screen.getByRole('img', { name: /高风险1条/ })).toBeInTheDocument();
  });

  it('renders the risk pulse as a review aid and preserves the selected filter state', () => {
    render(<ReportBoard report={report} scan={scan} selectedSeverity="HIGH" onSeveritySelect={vi.fn()} />);
    expect(screen.getByRole('img', { name: '风险指数 20 / 100，仅用于审阅排序' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '按 HIGH 筛选（1 条）' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('heading', { name: /先看证据密度/ })).toBeInTheDocument();
    expect(screen.getAllByText('仅用于审阅排序')).toHaveLength(1);
  });

  it('treats an empty findings array in a public summary as withheld detail, not zero risk', () => {
    const aggregateReport: FullReport = { ...report, artifact: { ...report.artifact, inventory: [] }, security: { ...report.security, findings: [] } };
    render(<ReportBoard report={aggregateReport} scan={scan} detailVisibility="aggregate" aggregates={{ categoryCounts: { credentials: 1 }, ruleCounts: { S002: 1 } }} />);
    expect(screen.getByRole('button', { name: '按 HIGH 筛选（1 条）' })).toBeInTheDocument();
    expect(screen.getByText('公开摘要未包含文件位置与证据；这些信息的缺失不表示文件中没有风险。')).toBeInTheDocument();
    expect(screen.getByRole('table', { name: '公开摘要的风险分类与对应发现数量' })).toHaveTextContent('credentials');
    expect(screen.queryByText('scripts/check.py')).not.toBeInTheDocument();
    expect(screen.queryByText('本次静态规则未命中文件风险；请继续查看检测覆盖。')).not.toBeInTheDocument();
  });

  it('does not endorse imported execution provenance or invent undisclosed versions', () => {
    const imported: FullReport = { ...report, provenance: { ...report.provenance, ruleset_version: '', policy_version: '' } };
    render(<ReportBoard report={imported} scan={scan} provenanceMode="imported" />);
    expect(screen.getByText('用户提供的报告 · 执行来源未验签 · 规则集 未披露')).toBeInTheDocument();
    expect(screen.getByText('策略 未披露')).toBeInTheDocument();
    expect(screen.queryByText('逐文件 SHA256 · 上传代码未执行')).not.toBeInTheDocument();
  });

  it('does not turn an absent stage duration into a zero latency measurement', () => {
    render(<ReportBoard report={report} scan={{ ...scan, stages: { schema: { status: 'PASSED', reason: null, coverage: {} } } }} />);
    expect(screen.getAllByText('未记录')).toHaveLength(2);
    expect(screen.queryByText('0 ms')).not.toBeInTheDocument();
    expect(screen.queryByText('合计 0 ms')).not.toBeInTheDocument();
  });

  it('keeps clean static findings separate from a comprehensive safety claim', () => {
    const clean: FullReport = { ...report, security: { ...report.security, findings: [], finding_counts: { critical: 0, high: 0, medium: 0, low: 0, info: 0 } } };
    render(<ReportBoard report={clean} scan={{ ...scan, finding_counts: clean.security.finding_counts }} />);
    expect(screen.getByRole('img', { name: '当前静态扫描未发现风险候选，不代表不存在风险' })).toBeInTheDocument();
    expect(screen.getByText('本次静态规则未命中文件风险；请继续查看检测覆盖。')).toBeInTheDocument();
    expect(screen.getByText('证据不足')).toBeInTheDocument();
    expect(screen.queryByText('安全可安装')).not.toBeInTheDocument();
  });

  it('prioritizes files with high risks and escapes untrusted path labels', () => {
    const maliciousPath = '<img src=x onerror=alert(1)>.py';
    const extra = { ...finding, severity: 'LOW' as const, fingerprint: 'low', file_path: 'low.py', category: 'documentation' };
    const data: FullReport = { ...report, security: { ...report.security, findings: [{ ...finding, file_path: maliciousPath }, extra], finding_counts: { high: 1, low: 1 } } };
    const { container } = render(<ReportBoard report={data} scan={scan} />);
    const table = screen.getByRole('table', { name: '各文件的发现数量、严重及高风险数量与风险分类数' });
    const rows = within(table).getAllByRole('row');
    expect(rows[1]).toHaveTextContent(maliciousPath);
    expect(rows[2]).toHaveTextContent('low.py');
    expect(container.querySelector('img[src="x"]')).toBeNull();
  });
});
