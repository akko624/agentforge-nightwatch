import { useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Descriptions, Empty, Progress, Select, Space, Statistic, Table, Tabs, Tag, Typography } from 'antd';
import { DownloadOutlined, ReloadOutlined, SwapOutlined } from '@ant-design/icons';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, downloadReport } from '../api/client';
import { dimensionLabels, ErrorNotice, FindingTable, isPending, percent, severityColors, StageTable, StatusTag, timeLabel } from '../components/shared';
import type { FullReport, InventoryEntry, Severity } from '../types';
import { ReportBoard } from '../components/report/ReportBoard';
import { SkillEvolutionAdvisor } from '../components/report/SkillEvolutionAdvisor';

interface QualityCheckRow { key: string; label: string; category: string; passed: boolean | null; reference: string }
const checkCategoryLabels: Record<string, string> = { official_required: '官方必填', official_optional: '官方可选', package_integrity: '包内完整性', platform_recommendation: '平台建议' };
function QualityChecks({ checks }: { checks: unknown[] }) {
  const rows: QualityCheckRow[] = checks.map((check, index) => {
    const value = check !== null && typeof check === 'object' && !Array.isArray(check) ? check as Record<string, unknown> : {};
    return { key: String(index), label: typeof value.label === 'string' ? value.label : '无法识别的检查项',
      category: typeof value.category === 'string' ? value.category : '', passed: typeof value.passed === 'boolean' ? value.passed : null,
      reference: typeof value.evidence_ref === 'string' ? value.evidence_ref : '' };
  });
  return <Table<QualityCheckRow> className="report-quality-checks" rowKey="key" size="small" pagination={false} dataSource={rows} scroll={{ x: 540 }} columns={[
    { title: '检查点', dataIndex: 'label' },
    { title: '依据类别', dataIndex: 'category', width: 95, render: (category: string) => checkCategoryLabels[category] ?? (category || '未分类') },
    { title: '结果', dataIndex: 'passed', width: 80, render: (passed: boolean | null) => <Tag color={passed === true ? 'green' : passed === false ? 'orange' : 'default'}>{passed === true ? '符合' : passed === false ? '待改进' : '未记录'}</Tag> },
    { title: '证据引用', dataIndex: 'reference', render: (reference: string) => <code>{reference || '未提供'}</code> },
  ]} />;
}

function QualityPanel({ report }: { report: FullReport }) {
  return <>
    <Alert type="info" showIcon message={report.quality.score === null ? '完整质量分未评测，不等于 0 分' : '完整质量分'} description="静态启发式只衡量结构与说明。功能正确性、触发率、任务成功率与稳定性必须来自真实宿主；未运行项不计为通过。" />
    <div className="quality-grid">{report.quality.dimensions.map((dimension) => <Card key={dimension.dimension} size="small" title={dimensionLabels[dimension.dimension] ?? dimension.dimension} extra={<span className="muted">权重 {percent(dimension.weight)}</span>}>
      <Space direction="vertical" size={12} style={{ width: '100%' }}><StatusTag status={dimension.status} /><Statistic title="本维度得分" value={dimension.score ?? '未评测'} precision={dimension.score === null ? undefined : 1} suffix={dimension.score === null ? undefined : '/ 100'} />
        {dimension.score !== null && <Progress percent={dimension.score} showInfo={false} strokeColor="#176b50" />}
        {dimension.reason && <Typography.Text type="secondary">{dimension.reason}</Typography.Text>}
        {dimension.metric && <Typography.Text type="secondary">指标：{dimension.metric}</Typography.Text>}
        {!!dimension.checks?.length && <details><summary>查看检查依据（{dimension.checks.length} 项）</summary><QualityChecks checks={dimension.checks} /></details>}
        {dimension.runner_version && <Typography.Text type="secondary">评测器版本：{dimension.runner_version}</Typography.Text>}
      </Space>
    </Card>)}</div>
    {report.quality.reasons.map((reason, index) => <Typography.Paragraph type="secondary" key={index}>{reason}</Typography.Paragraph>)}
  </>;
}

function InventoryPanel({ report }: { report: FullReport }) {
  return <><Typography.Paragraph type="secondary">所有条目仅作为数据读取。不可解析文件、隐藏文件和可执行标记均纳入清单；没有执行任何上传文件。</Typography.Paragraph><Table<InventoryEntry> size="small" rowKey="path" dataSource={report.artifact.inventory} pagination={{ pageSize: 20, showSizeChanger: false }} scroll={{ x: 900 }} columns={[
    { title: '相对路径', dataIndex: 'path', render: (value: string) => <code>{value}</code> },
    { title: '大小', dataIndex: 'size', width: 100, render: (value: number) => `${value.toLocaleString()} B` },
    { title: '类型与标记', dataIndex: 'kind', width: 210, render: (kind: string, item) => <Space wrap size={2}><Tag>{kind}</Tag>{item.hidden && <Tag>隐藏</Tag>}{item.executable && <Tag color="orange">可执行标记</Tag>}{!item.parseable && <Tag color="orange">不可解析</Tag>}</Space> },
    { title: 'SHA256', dataIndex: 'sha256', render: (value: string) => <code className="hash">{value}</code> },
  ]} /></>;
}

export default function ReportPage() {
  const { id = '' } = useParams(); const navigate = useNavigate();
  const [severity, setSeverity] = useState<Severity>(); const [engine, setEngine] = useState<string>(); const [page, setPage] = useState(1);
  const [activeTab, setActiveTab] = useState('security');
  const detailsRef = useRef<HTMLDivElement>(null);
  const summary = useQuery({ queryKey: ['scan', id], queryFn: () => api.scan(id), enabled: !!id, refetchInterval: (query) => query.state.data && isPending(query.state.data.status) ? 2_000 : false });
  const ready = summary.data?.status === 'PARTIAL' || summary.data?.status === 'COMPLETED';
  const report = useQuery({ queryKey: ['report', id], queryFn: () => api.report(id), enabled: ready, retry: false });
  const findings = useQuery({ queryKey: ['findings', id, severity, engine, page], queryFn: () => api.findings(id, { severity, engine, limit: 20, offset: (page - 1) * 20 }), enabled: ready });
  const download = useMutation({ mutationFn: () => downloadReport(id) });
  const rescan = useMutation({ mutationFn: () => api.createScan(summary.data!.version_id, undefined, true), onSuccess: (scan) => navigate(`/scans/${scan.scan_id}`) });
  if (summary.isLoading) return <Card loading title="正在读取扫描状态" />;
  if (summary.isError) return <><Link to="/">← 返回工作台</Link><ErrorNotice error={summary.error} title="无法读取扫描" /></>;
  const scan = summary.data;
  if (!scan) return <Empty description="没有扫描数据" />;
  const engineNames = Array.from(new Set(report.data?.security.findings.map((finding) => finding.engine) ?? []));
  return <>
    <Link to="/" className="back-link">← 返回扫描工作台</Link>
    <div className="page-heading"><div><Typography.Text className="eyebrow">SCAN REPORT</Typography.Text><Typography.Title>{scan.skill_name}</Typography.Title><Space wrap><StatusTag status={scan.status} /><Typography.Text type="secondary">版本 {scan.version_label ?? '未声明'} · {timeLabel(scan.created_at)}</Typography.Text></Space></div><Space wrap><Button icon={<SwapOutlined />} disabled={!ready} onClick={() => navigate(`/compare?left=${scan.scan_id}`)}>对比版本</Button><Button icon={<ReloadOutlined />} onClick={() => rescan.mutate()} loading={rescan.isPending} disabled={isPending(scan.status)}>重新扫描</Button><Button aria-label="导出 JSON" type="primary" icon={<DownloadOutlined />} disabled={!report.data} loading={download.isPending} onClick={() => download.mutate()}>导出 JSON</Button></Space></div>
    <ErrorNotice error={download.error ?? rescan.error} />
    {isPending(scan.status) && <Alert className="section-gap" type="info" showIcon message={scan.status === 'QUEUED' ? '任务已入队，等待独立 Worker' : 'Worker 正在分析'} description="每 2 秒刷新状态。若长时间排队，请确认 Worker 与队列服务正常。上传的 Skill 代码不会执行。" />}
    {scan.status === 'FAILED' && <Alert className="section-gap" type="error" showIcon message="扫描失败，未授予安全结论" description={<span>错误码：<code>{scan.error_code ?? 'UNKNOWN'}</code>。已尝试 {scan.attempts} 次。可以在修复服务或工件后重新扫描，失败记录会保留。</span>} />}
    {scan.status === 'PARTIAL' && <Alert className="section-gap" showIcon type="warning" message="部分完成：不能据此判定全面安全" description="静态检测可以查看；动态、语义、真实任务等未运行能力请逐项查看。发布门禁与质量覆盖分别报告。" />}
    {report.data ? <ReportBoard report={report.data} scan={scan} selectedSeverity={severity} onSeveritySelect={(value) => { setSeverity(value); setEngine(undefined); setPage(1); setActiveTab('security'); detailsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }} /> : <div className="metric-grid section-gap"><Card size="small"><Statistic title="局部静态质量" value={scan.static_quality_subscore ?? '未评测'} precision={scan.static_quality_subscore === null ? undefined : 1} suffix={scan.static_quality_subscore === null ? undefined : '/ 100'} /><div className="metric-note">完整质量分：{scan.quality_score === null ? '未评测（null）' : scan.quality_score}</div></Card><Card size="small"><Statistic title="质量评测覆盖" value={Math.round(scan.quality_coverage * 100)} suffix="%" /><div className="metric-note">已完成维度的原始权重之和</div></Card><Card size="small"><div className="metric-label">安全结论 / 风险指数</div><StatusTag status={scan.security_verdict} /><div className="metric-note">{scan.security_risk_index ?? '—'} / 100 · 仅用于审阅排序</div></Card><Card size="small"><div className="metric-label">发布门禁</div><StatusTag status={scan.release_decision} /><div className="metric-note">策略 {scan.policy_version} · 不等于绝对安全</div></Card></div>}
    {report.data && <Alert className="section-gap" type={scan.release_decision === 'BLOCK' ? 'error' : 'info'} showIcon message="门禁依据" description={<Space direction="vertical" size={4}><span>必需阶段：{report.data.decision.required_stages.map((stage) => stage).join('、')}</span><span>{report.data.decision.reasons.join('；')}</span><span>{report.data.decision.scope}</span></Space>} />}
    <Card title="检测覆盖与阶段状态" className="section-gap"><StageTable stages={scan.stages} /><Typography.Paragraph type="secondary" className="section-gap">UNAVAILABLE、ERROR、TIMEOUT、PARTIAL 均不会视为已通过。动态与模型能力未配置时不会使用本机执行替代。</Typography.Paragraph></Card>
    <ErrorNotice error={report.error} title="完整报告暂不可用" />
    {ready && <div ref={detailsRef} id="report-details"><Card className="section-gap" loading={report.isLoading}><Tabs activeKey={activeTab} onChange={setActiveTab} items={[
      { key: 'security', label: `安全发现（${Object.values(scan.finding_counts).reduce((sum, value) => sum + value, 0)}）`, children: <><div className="filter-bar"><Select aria-label="风险级别筛选" placeholder="全部风险级别" allowClear value={severity} onChange={(value) => { setSeverity(value); setPage(1); }} style={{ minWidth: 190 }} options={Object.keys(severityColors).map((value) => ({ value, label: value }))} /><Select aria-label="检测引擎筛选" placeholder="全部引擎" allowClear value={engine} onChange={(value) => { setEngine(value); setPage(1); }} style={{ minWidth: 190 }} options={engineNames.map((value) => ({ value, label: value }))} /><Typography.Text type="secondary">展开行查看证据与整改建议 · 当前 {findings.data?.total ?? 0} 条</Typography.Text></div><ErrorNotice error={findings.error} /><FindingTable findings={findings.data?.items ?? []} loading={findings.isLoading} pagination={{ current: page, pageSize: 20, total: findings.data?.total ?? 0, showSizeChanger: false, onChange: setPage }} />{report.data?.security.limitations.map((limitation, index) => <Typography.Paragraph type="secondary" className="section-gap" key={index}>{limitation}</Typography.Paragraph>)}</> },
      { key: 'evolution', label: 'Skill 改进工作台', children: report.data && <SkillEvolutionAdvisor report={report.data} scan={scan} /> },
      { key: 'quality', label: '质量维度与依据', children: report.data && <QualityPanel report={report.data} /> },
      { key: 'files', label: `文件清单（${report.data?.artifact.files ?? 0}）`, children: report.data && <InventoryPanel report={report.data} /> },
      { key: 'provenance', label: '规范与来源', children: report.data && <><Descriptions column={1} bordered size="small" items={[
        { key: 'schema', label: '规范校验', children: <StatusTag status={report.data.compliance.status} /> },
        { key: 'sha', label: '工件 SHA256', children: <code className="hash">{scan.artifact_sha256}</code> },
        { key: 'rules', label: '规则集版本', children: report.data.provenance.ruleset_version },
        { key: 'ruleshash', label: '规则集 SHA256', children: <code className="hash">{report.data.provenance.ruleset_sha256}</code> },
        { key: 'source', label: '扫描器源码 SHA256', children: <code className="hash">{report.data.provenance.scanner_source_sha256}</code> },
        { key: 'policy', label: '策略版本', children: report.data.provenance.policy_version },
        { key: 'engines', label: '扫描器版本', children: <pre className="evidence">{JSON.stringify(scan.scanner_versions, null, 2)}</pre> },
      ]} /><Typography.Title level={5}>权限声明与有效权限</Typography.Title><Alert type="info" showIcon message="作者声明不代表授权；当前没有执行层权限强制验证" description="有效权限取平台允许权限与审批声明的交集。执行器不可用时，不能将声明视为已在运行时执行。" /><pre className="evidence">{JSON.stringify(report.data.permissions, null, 2)}</pre><Typography.Title level={5}>规范问题</Typography.Title>{report.data.compliance.issues.length ? <ul>{report.data.compliance.issues.map((issue, index) => <li key={index}><code>{issue.file_path}:{issue.line}</code> · {issue.code}</li>)}</ul> : <Typography.Paragraph>未发现规范问题。</Typography.Paragraph>}<details><summary>查看解析清单、策略快照与限额</summary><pre className="evidence">{JSON.stringify({ manifest: report.data.artifact.manifest, policy: report.data.provenance.policy_snapshot, limits: report.data.provenance.limits }, null, 2)}</pre></details></> },
      { key: 'logs', label: '执行记录', children: report.data && <Table size="small" rowKey="stage" pagination={false} dataSource={report.data.logs} columns={[{ title: '事件', dataIndex: 'event' }, { title: '阶段', dataIndex: 'stage' }, { title: '状态', dataIndex: 'status', render: (value: string) => <StatusTag status={value} /> }, { title: '耗时 / ms', dataIndex: 'duration_ms' }, { title: '原因', dataIndex: 'reason' }]} scroll={{ x: 700 }} /> },
    ]} /></Card></div>}
    <Typography.Paragraph type="secondary" className="hash">Scan ID：{scan.scan_id} · 工件 SHA256：{scan.artifact_sha256}</Typography.Paragraph>
  </>;
}
