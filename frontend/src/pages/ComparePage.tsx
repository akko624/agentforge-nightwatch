import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Descriptions, Select, Space, Statistic, Table, Tabs, Typography } from 'antd';
import { SwapOutlined } from '@ant-design/icons';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { dimensionLabels, ErrorNotice, FindingDetails, FindingTable, percent, StageTable, StatusTag, timeLabel } from '../components/shared';
import type { ScanSummary } from '../types';

const scoreLabel = (value: number | null) => value === null ? '未评测' : value.toFixed(1);
export default function ComparePage() {
  const [params, setParams] = useSearchParams();
  const [left, setLeft] = useState(params.get('left') ?? ''); const [right, setRight] = useState(params.get('right') ?? '');
  const scans = useQuery({ queryKey: ['scans', 'compare'], queryFn: () => api.listScans({ limit: 100 }) });
  const linkedLeft = useQuery({ queryKey: ['scan', params.get('left')], queryFn: () => api.scan(params.get('left')!), enabled: !!params.get('left') });
  const linkedRight = useQuery({ queryKey: ['scan', params.get('right')], queryFn: () => api.scan(params.get('right')!), enabled: !!params.get('right') });
  const candidates = Array.from(new Map([...(scans.data?.items ?? []), ...[linkedLeft.data, linkedRight.data].filter((value): value is ScanSummary => !!value)].map((scan) => [scan.scan_id, scan])).values()).filter((scan) => scan.status === 'PARTIAL' || scan.status === 'COMPLETED');
  const chosen = candidates.find((scan) => scan.scan_id === left);
  const option = (scan: ScanSummary) => ({ value: scan.scan_id, label: `${scan.skill_name} · ${scan.version_label ?? '未声明版本'} · ${scan.artifact_sha256.slice(0, 8)} · ${timeLabel(scan.created_at)} · ${scan.scan_id.slice(0, 8)}` });
  const diff = useQuery({ queryKey: ['compare', params.get('left'), params.get('right')], queryFn: () => api.compare(params.get('left')!, params.get('right')!), enabled: !!params.get('left') && !!params.get('right'), retry: false });
  return <>
    <Link to="/" className="back-link">← 返回扫描工作台</Link><Typography.Text className="eyebrow">VERSION COMPARISON</Typography.Text><Typography.Title>变化比结论更值得追溯。</Typography.Title><Typography.Paragraph type="secondary">选择同一个 Skill 的两次已生成报告的扫描，查看风险发现、质量依据与覆盖差异。</Typography.Paragraph>
    <Card className="section-gap"><div className="compare-select"><div><label className="field-label" htmlFor="compare-left">基准扫描</label><Select id="compare-left" aria-label="基准扫描" showSearch optionFilterProp="label" placeholder="选择基准扫描" value={left || undefined} onChange={(value) => { setLeft(value); setRight(''); }} options={candidates.map(option)} loading={scans.isLoading} style={{ width: '100%' }} /></div><SwapOutlined className="compare-arrow" /><div><label className="field-label" htmlFor="compare-right">目标扫描</label><Select id="compare-right" aria-label="目标扫描" showSearch optionFilterProp="label" placeholder={chosen ? '选择同 Skill 的另一次扫描' : '先选择基准扫描'} value={right || undefined} onChange={setRight} disabled={!chosen} options={candidates.filter((scan) => scan.skill_id === chosen?.skill_id && scan.scan_id !== left).map(option)} style={{ width: '100%' }} /></div><Button type="primary" size="large" loading={diff.isFetching} disabled={!left || !right || left === right} onClick={() => setParams({ left, right })}>比较报告</Button></div><Typography.Paragraph type="secondary" className="section-gap">选择器显示最近 100 次扫描及链接指定的扫描。仅比较同 Skill；不同策略或规则集会标记可比性限制。</Typography.Paragraph><ErrorNotice error={scans.error ?? linkedLeft.error ?? linkedRight.error} /></Card>
    <ErrorNotice error={diff.error} title="无法比较这两次扫描" />
    {diff.data && <>
      <div className="comparison-head section-gap">{[diff.data.left, diff.data.right].map((scan, index) => <Card key={index} size="small" title={index === 0 ? '基准扫描' : '目标扫描'} extra={<Link to={`/scans/${scan.scan_id}`}>查看报告 →</Link>}><Typography.Title level={4}>{scan.skill_name} / {scan.version_label ?? '未声明版本'}</Typography.Title><Space wrap><StatusTag status={scan.status} /><StatusTag status={scan.release_decision} /></Space><Descriptions column={1} size="small" className="section-gap" items={[{ key: 'time', label: '时间', children: timeLabel(scan.created_at) }, { key: 'quality', label: '质量覆盖', children: percent(scan.quality_coverage) }, { key: 'policy', label: '策略版本', children: scan.policy_version }, { key: 'sha', label: '工件 SHA256', children: <code className="hash">{scan.artifact_sha256}</code> }]} /></Card>)}</div>
      <Alert className="section-gap" showIcon type={diff.data.comparability.comparable ? 'info' : 'warning'} message={diff.data.comparability.comparable ? '当前扫描设置可比；静态结果仍有覆盖限制' : '检测设置存在差异，避免直接推断质量变好或风险降低'} description={<Space direction="vertical" size={3}><span>策略变化：{diff.data.policy_changed ? '是' : '否'} · 规则集变化：{diff.data.ruleset_changed ? '是' : '否'} · 扫描器变化：{diff.data.scanner_changed ? '是' : '否'}</span>{[...diff.data.comparability.reasons, ...diff.data.warnings].map((reason, index) => <span key={index}>{reason}</span>)}</Space>} />
      <div className="metric-grid section-gap"><Card size="small"><Statistic title="新增发现" value={diff.data.new_findings.length} valueStyle={{ color: '#ad3f2e' }} /></Card><Card size="small"><Statistic title="已解决发现" value={diff.data.resolved_findings.length} valueStyle={{ color: '#176b50' }} /></Card><Card size="small"><Statistic title="持续发现" value={diff.data.unchanged_findings.length} /></Card><Card size="small"><Statistic title="证据变化" value={diff.data.changed_evidence.length} /></Card></div>
      <Card className="section-gap"><Tabs items={[
        { key: 'new', label: `新增（${diff.data.new_findings.length}）`, children: <FindingTable findings={diff.data.new_findings} /> },
        { key: 'resolved', label: `已解决（${diff.data.resolved_findings.length}）`, children: <FindingTable findings={diff.data.resolved_findings} /> },
        { key: 'unchanged', label: `持续（${diff.data.unchanged_findings.length}）`, children: <FindingTable findings={diff.data.unchanged_findings} /> },
        { key: 'changed', label: `证据变化（${diff.data.changed_evidence.length}）`, children: <>{diff.data.changed_evidence.length === 0 && <Typography.Paragraph>没有识别到证据变化。</Typography.Paragraph>}{diff.data.changed_evidence.map((item, index) => <Card key={index} size="small" title={`${item.left.rule_id} · ${item.left.file_path}`} className="section-gap"><Typography.Title level={5}>基准证据</Typography.Title><FindingDetails finding={item.left} /><Typography.Title level={5}>目标证据</Typography.Title><FindingDetails finding={item.right} /></Card>)}</> },
        { key: 'quality', label: '质量维度变化', children: <><Alert className="section-gap" type="info" showIcon message="未评测值保留为空，不计算虚构提升" /><Table rowKey="dimension" pagination={false} dataSource={diff.data.quality_changes} columns={[{ title: '维度', dataIndex: 'dimension', render: (value: string) => dimensionLabels[value] ?? value }, { title: '基准得分', dataIndex: 'left_score', render: scoreLabel }, { title: '目标得分', dataIndex: 'right_score', render: scoreLabel }, { title: '变化', dataIndex: 'delta', render: (value: number | null) => value === null ? '不适用' : `${value > 0 ? '+' : ''}${value.toFixed(1)}` }]} /></> },
        { key: 'coverage', label: '检测覆盖变化', children: <><Typography.Title level={5}>基准阶段</Typography.Title><StageTable stages={diff.data.coverage_changes.left} /><Typography.Title level={5}>目标阶段</Typography.Title><StageTable stages={diff.data.coverage_changes.right} /></> },
      ]} /></Card>
    </>}
  </>;
}
