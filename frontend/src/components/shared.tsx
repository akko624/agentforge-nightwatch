import { Alert, Descriptions, Empty, Space, Table, Tag, Typography } from 'antd';
import type { TableProps } from 'antd';
import type { Finding, StageResult } from '../types';
import { ApiError } from '../api/client';

const statusLabels: Record<string, [string, string]> = {
  QUEUED: ['排队中', 'default'], RUNNING: ['运行中', 'processing'], COMPLETED: ['已完成', 'green'],
  PARTIAL: ['部分完成', 'orange'], FAILED: ['失败', 'red'], PASSED: ['已通过', 'green'], FINDINGS: ['存在发现', 'orange'],
  NOT_RUN: ['未运行', 'default'], UNAVAILABLE: ['不可用', 'default'], ERROR: ['错误', 'red'], TIMEOUT: ['超时', 'red'],
  ALLOW: ['当前门禁允许', 'green'], REVIEW: ['需要审查', 'orange'], BLOCK: ['阻断发布', 'red'], INCOMPLETE: ['证据不足', 'orange'],
  PASS: ['当前检查通过', 'green'], UNKNOWN: ['未知', 'default'],
};
export const stageLabels: Record<string, string> = { schema: '规范校验', static: '静态安全', dependencies: '依赖漏洞', semantic: '语义检测', dynamic: '动态沙箱', quality: '质量评测' };
export const dimensionLabels: Record<string, string> = { conformance: '规范符合性', maintainability: '可理解性与可维护性', correctness: '功能正确性', reliability: '稳定性与效率' };
export const severityColors: Record<string, string> = { INFO: 'default', LOW: 'blue', MEDIUM: 'gold', HIGH: 'orange', CRITICAL: 'red' };
export const isPending = (status: string) => status === 'QUEUED' || status === 'RUNNING';
export const percent = (value: number) => `${Math.round(value * 100)}%`;
export function timeLabel(value: string | null) {
  if (!value) return '—';
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
  return new Date(normalized).toLocaleString('zh-CN');
}
export function StatusTag({ status }: { status: string }) { const label = statusLabels[status]; return <Tag color={label?.[1]}>{label ? `${label[0]} · ${status}` : status}</Tag>; }
export function ErrorNotice({ error, title = '请求未完成' }: { error: Error | null; title?: string }) {
  if (!error) return null;
  return <Alert showIcon type="error" className="section-gap" message={title} description={<Space direction="vertical" size={3}><span>{error.message}</span>{error instanceof ApiError && <><code>{error.code}</code>{error.requestId && <Typography.Text type="secondary">请求 ID：{error.requestId}</Typography.Text>}</>}</Space>} />;
}
export function StageTable({ stages }: { stages: Record<string, StageResult> }) {
  return <Table size="small" rowKey="name" pagination={false} dataSource={Object.entries(stages).map(([name, result]) => ({ name, ...result }))} expandable={{ columnTitle: '覆盖详情', rowExpandable: (row) => Object.keys(row.coverage ?? {}).length > 0, expandedRowRender: (row) => <pre className="evidence">{JSON.stringify(row.coverage, null, 2)}</pre> }} columns={[
    { title: '检测阶段', dataIndex: 'name', render: (name: string) => stageLabels[name] ?? name },
    { title: '状态', dataIndex: 'status', render: (status: string) => <StatusTag status={status} /> },
    { title: '说明 / 局限', dataIndex: 'reason', render: (reason: string | null, row) => reason || (['PASSED', 'FINDINGS'].includes(row.status) ? '检查已完成；结果仅限本阶段覆盖范围' : '未提供更多说明；请依据阶段状态判断覆盖') },
    { title: '耗时', dataIndex: 'duration_ms', width: 100, render: (ms: number) => `${ms} ms` },
  ]} scroll={{ x: 650 }} />;
}
export function FindingDetails({ finding }: { finding: Finding }) {
  return <div className="finding-detail">
    <Descriptions size="small" column={{ xs: 1, sm: 2 }} items={[
      { key: 'location', label: '文件位置', children: <code>{finding.file_path}:{finding.line_start}–{finding.line_end}</code> },
      { key: 'confidence', label: '置信度', children: finding.confidence },
      { key: 'version', label: '规则 / 引擎版本', children: `${finding.matched_rule_version} / ${finding.engine_version}` },
      { key: 'status', label: '审查状态', children: finding.status },
    ]} />
    <Typography.Text strong>脱敏证据（纯文本）</Typography.Text><pre className="evidence">{finding.evidence_excerpt || '无文本证据'}</pre>
    <Typography.Paragraph><strong>整改建议：</strong>{finding.remediation}</Typography.Paragraph>
    {finding.context_note && <Alert type="warning" showIcon message="可能存在上下文或误报边界" description={finding.context_note} />}
    <Typography.Text type="secondary" className="hash">Fingerprint: {finding.fingerprint}</Typography.Text>
  </div>;
}
export function FindingTable({ findings, loading = false, pagination = false }: { findings: Finding[]; loading?: boolean; pagination?: TableProps<Finding>['pagination'] }) {
  return <Table<Finding> size="middle" rowKey="fingerprint" loading={loading} pagination={pagination} dataSource={findings} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前范围内没有发现；这不表示不存在风险。" /> }}
    expandable={{ expandedRowRender: (finding) => <FindingDetails finding={finding} />, columnTitle: '证据', expandRowByClick: true }}
    columns={[
      { title: '级别', dataIndex: 'severity', width: 110, render: (severity: string) => <Tag color={severityColors[severity]}>{severity}</Tag> },
      { title: '规则 / 分类', dataIndex: 'rule_id', width: 150, render: (id: string, finding: Finding) => <Space direction="vertical" size={0}><strong>{id}</strong><Typography.Text type="secondary">{finding.category}</Typography.Text></Space> },
      { title: '发现与位置', dataIndex: 'message', render: (message: string, finding: Finding) => <Space direction="vertical" size={3}><span>{message}</span><code className="muted">{finding.file_path}:{finding.line_start}</code></Space> },
      { title: '引擎', dataIndex: 'engine', width: 145 },
    ]} scroll={{ x: 780 }} />;
}
