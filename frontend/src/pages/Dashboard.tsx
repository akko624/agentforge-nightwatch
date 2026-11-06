import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Empty, Input, Select, Space, Table, Typography } from 'antd';
import { ArrowRightOutlined, ReloadOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { ErrorNotice, isPending, percent, StatusTag, timeLabel } from '../components/shared';
import type { ScanSummary } from '../types';

export default function Dashboard() {
  const [q, setQ] = useState(''); const [status, setStatus] = useState<string>(); const [page, setPage] = useState(1);
  const scans = useQuery({ queryKey: ['scans', q, status, page], queryFn: () => api.listScans({ q, status, offset: (page - 1) * 10, limit: 10 }),
    refetchInterval: (query) => query.state.data?.items.some((scan) => isPending(scan.status)) ? 2_000 : 10_000 });
  return <>
    <div className="page-heading"><div><Typography.Text className="eyebrow">AGENT ARTIFACT ASSURANCE PLATFORM</Typography.Text><Typography.Title>让 Agent 工件可审查、可演进、可交付。</Typography.Title><Typography.Paragraph type="secondary">Skill 是第一个已上线工件类型；平台统一呈现安全证据、质量覆盖、发布门禁和下一轮改进路线。</Typography.Paragraph></div><Link to="/upload"><Button type="primary" size="large" icon={<ArrowRightOutlined />}>导入首个工件</Button></Link></div>
    <div className="principle-grid"><div><strong>当前：Skill 安全与质量</strong><span>安全摄入、异步扫描、版本对比与证据报告已可运行。</span></div><div><strong>已具备：进化建议闭环</strong><span>报告生成 P0/P1/P2 改进简报；候选改动仍需人工确认。</span></div><div><strong>路线：更多 Agent 工件</strong><span>工作流、提示包和连接器将复用同一证据与门禁模型，尚未开放上传。</span></div></div>
    <Card className="section-gap" title="最近扫描" extra={<Button aria-label="刷新扫描列表" icon={<ReloadOutlined />} onClick={() => void scans.refetch()}>刷新</Button>}>
      <div className="filter-bar"><Input.Search aria-label="搜索 Skill 名称" placeholder="搜索 Skill 名称" allowClear onSearch={(value) => { setQ(value); setPage(1); }} style={{ maxWidth: 360 }} /><Select aria-label="扫描状态筛选" placeholder="全部状态" allowClear value={status} style={{ minWidth: 185 }} onChange={(value) => { setStatus(value); setPage(1); }} options={['QUEUED', 'RUNNING', 'COMPLETED', 'PARTIAL', 'FAILED'].map((value) => ({ value, label: value }))} /><Typography.Text type="secondary">共 {scans.data?.total ?? 0} 次扫描</Typography.Text></div>
      <ErrorNotice error={scans.error} title="扫描列表加载失败" />
      <Table<ScanSummary> rowKey="scan_id" dataSource={scans.data?.items ?? []} loading={scans.isLoading} locale={{ emptyText: <Empty description={q || status ? '没有符合筛选条件的扫描' : '暂无扫描，上传第一个 Skill 开始检测。'} /> }} scroll={{ x: 1080 }} pagination={{ current: page, pageSize: 10, total: scans.data?.total ?? 0, showSizeChanger: false, onChange: setPage }} columns={[
        { title: 'Skill / 版本', dataIndex: 'skill_name', render: (name: string, scan) => <Space direction="vertical" size={2}><Link className="skill-link" to={`/scans/${scan.scan_id}`}>{name}</Link><Typography.Text type="secondary">{scan.version_label ?? '未声明版本'} · {scan.artifact_sha256.slice(0, 10)}</Typography.Text></Space> },
        { title: '扫描状态', dataIndex: 'status', width: 155, render: (value: string) => <StatusTag status={value} /> },
        { title: '局部静态质量', dataIndex: 'static_quality_subscore', width: 150, render: (score: number | null, scan) => <Space direction="vertical" size={1}><strong>{score === null ? '—' : `${score.toFixed(1)} / 100`}</strong><Typography.Text type="secondary">覆盖 {percent(scan.quality_coverage)}</Typography.Text></Space> },
        { title: '风险发现', dataIndex: 'finding_counts', width: 130, render: (counts: Record<string, number>) => <span>{Object.values(counts).reduce((sum, value) => sum + value, 0)} 条 <small className="muted">H:{counts.high ?? 0} / C:{counts.critical ?? 0}</small></span> },
        { title: '发布门禁', dataIndex: 'release_decision', width: 180, render: (value: string) => <StatusTag status={value} /> },
        { title: '扫描时间', dataIndex: 'created_at', width: 175, render: timeLabel },
        { title: '', key: 'action', width: 75, render: (_, scan) => <Link to={`/scans/${scan.scan_id}`}>报告 →</Link> },
      ]} />
    </Card>
    <Alert type="info" showIcon message="当前 MVP 以确定性静态检测为主" description="局部静态质量分只衡量结构与说明质量。缺少真实宿主任务与稳定性数据时，完整质量分保持未评测；没有发现也不代表完全安全。" />
  </>;
}
