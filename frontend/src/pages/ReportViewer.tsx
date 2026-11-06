import { useRef, useState } from 'react';
import { Alert, Button, Card, Empty, Select, Space, Table, Typography } from 'antd';
import { DownloadOutlined, FileSearchOutlined, FolderOpenOutlined } from '@ant-design/icons';
import { FindingTable, StageTable } from '../components/shared';
import { ReportBoard } from '../components/report/ReportBoard';
import { makePublicSummary, MAX_REPORT_BYTES, parseLocalReport, ReportImportError, type LocalDocument } from '../reports/localReport';
import type { Severity } from '../types';
import './viewer.css';

function bootstrap(): { document: LocalDocument | null; error: string | null } {
  const embedded = document.getElementById('sqsp-public-summary');
  if (!embedded?.textContent) return { document: null, error: null };
  try {
    const data = parseLocalReport(embedded.textContent);
    if (data.mode !== 'aggregate') throw new Error('Only public summaries may be embedded');
    return { document: data, error: null };
  } catch { return { document: null, error: '嵌入的公开摘要无效，未展示任何报告结论。' }; }
}

export default function ReportViewer() {
  const [initial] = useState(bootstrap);
  const [local, setLocal] = useState<LocalDocument | null>(initial.document);
  const [error, setError] = useState<string | null>(initial.error);
  const [busy, setBusy] = useState(false);
  const [severity, setSeverity] = useState<Severity>();
  const [page, setPage] = useState(1);
  const input = useRef<HTMLInputElement>(null);
  const generation = useRef(0);

  async function selectFile(file?: File) {
    if (!file) return;
    const current = ++generation.current;
    setBusy(true); setError(null); setLocal(null); setSeverity(undefined); setPage(1);
    try {
      if (file.size > MAX_REPORT_BYTES) throw new ReportImportError('REPORT_TOO_LARGE', '报告超过 5 MiB 限制。');
      if (!file.name.toLowerCase().endsWith('.json')) throw new ReportImportError('INVALID_FILE', '请选择 .json 报告文件；此入口不扫描 ZIP。');
      const parsed = parseLocalReport(await file.text());
      if (current === generation.current) setLocal(parsed);
    } catch (cause) {
      if (current === generation.current) setError(cause instanceof ReportImportError ? `${cause.message}（${cause.code}）` : '无法读取报告文件，请重新选择。');
    } finally { if (current === generation.current) setBusy(false); if (input.current) input.current.value = ''; }
  }

  function clear() {
    generation.current += 1; setLocal(null); setError(null); setBusy(false); setSeverity(undefined); setPage(1);
  }
  function downloadSummary() {
    if (!local) return;
    const summary = makePublicSummary(local);
    const objectUrl = URL.createObjectURL(new Blob([JSON.stringify(summary, null, 2)], { type: 'application/json;charset=utf-8' }));
    const anchor = document.createElement('a'); anchor.href = objectUrl; anchor.download = 'sqsp-public-summary.json';
    document.body.appendChild(anchor); anchor.click(); anchor.remove(); window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }
  const findings = local?.report.security.findings.filter((finding) => !severity || finding.severity === severity) ?? [];
  return <div className="report-viewer">
    <div className="viewer-heading"><div><Typography.Text className="eyebrow">REPORT STUDIO / LOCAL VIEWER</Typography.Text><Typography.Title>让证据成为报告的中心。</Typography.Title><Typography.Paragraph type="secondary">在浏览器中查看 SQSP JSON。报告仅保留在当前页面内存中；重新载入后，手动导入的文件需要重新选择。</Typography.Paragraph></div><Space wrap><input aria-label="选择本地 JSON 报告" ref={input} type="file" accept=".json,application/json" hidden onChange={(event) => void selectFile(event.target.files?.[0])} /><Button icon={<FolderOpenOutlined />} type="primary" loading={busy} onClick={() => input.current?.click()}>选择本地 JSON</Button>{local && <Button onClick={clear}>清除当前报告</Button>}</Space></div>
    <Alert className="section-gap" type="info" showIcon message="本地查看，无需上传报告" description={initial.document ? '此页面内置发布者提供的聚合摘要，选择本地 JSON 可替换当前查看内容。此入口不连接扫描 API、不写入浏览器持久存储，也不执行 Skill。' : '此入口只读取 JSON，不能生成新的安全扫描结果。它不连接扫描 API、不把文件写入浏览器持久存储，也不执行 Skill。分享查看器链接时，对方仍需自己的报告文件。'} />
    {error && <Alert className="section-gap" type="error" showIcon message="报告未载入" description={error} />}
    {!local && <Card className="section-gap viewer-empty"><FileSearchOutlined className="viewer-empty-icon" /><Typography.Title level={3}>选择一份报告，展开验证看板</Typography.Title><Typography.Paragraph>支持 SQSP 完整 JSON 或聚合摘要，最大 5 MiB。图表由文件中的记录生成，未测项保留未知。</Typography.Paragraph><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未导入报告" /></Card>}
    {local && <>
      <Alert className="section-gap" type="warning" showIcon message="用户提供的报告，未经平台验签" description="图表反映导入文件中的声明。此页面无法验证扫描是否真实执行、文件是否被修改，不能作为安全认证。常见密钥格式会再次遮盖，但不能保证识别所有敏感信息。" />
      <div className="viewer-report-heading"><div><Typography.Text type="secondary">{local.mode === 'aggregate' ? '聚合摘要 · 原始名称与证据已省略' : '本地完整报告'}</Typography.Text><Typography.Title level={2}>{local.report.artifact.name}</Typography.Title></div><Button icon={<DownloadOutlined />} onClick={downloadSummary}>下载聚合摘要</Button></div>
      <ReportBoard report={local.report} scan={local.scan} provenanceMode="imported" detailVisibility={local.mode} aggregates={local.aggregates} onSeveritySelect={local.mode === 'full' ? (value) => { setSeverity(value); setPage(1); document.getElementById('viewer-evidence')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); } : undefined} />
      <Alert className="section-gap" type="info" showIcon message="分享前，先确认披露范围" description="聚合摘要只保留风险计数、规则与分类计数、阶段状态和质量数值，不含原始名称、路径、证据、标识、hash、权限和日志。一条链接直接展示同份报告，需要另外托管经过复核的摘要副本；静态托管不等于没有存储。" />
      {local.mode === 'full' ? <Card className="section-gap" id="viewer-evidence" title="本地证据明细" extra={<Select aria-label="本地风险筛选" allowClear placeholder="全部级别" value={severity} onChange={(value) => { setSeverity(value); setPage(1); }} style={{ minWidth: 150 }} options={['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'].map((value) => ({ value, label: value }))} />}><FindingTable findings={findings.slice((page - 1) * 20, page * 20)} pagination={{ current: page, pageSize: 20, total: findings.length, showSizeChanger: false, onChange: setPage }} /></Card> : <Card className="section-gap" title="公开摘要的规则计数"><Table rowKey="rule" size="small" pagination={false} dataSource={Object.entries(local.aggregates?.ruleCounts ?? {}).map(([rule, count]) => ({ rule, count }))} columns={[{ title: '规则', dataIndex: 'rule' }, { title: '发现数', dataIndex: 'count' }]} /><Typography.Paragraph type="secondary">原始位置与证据未包含在摘要中，无法在此复核；空证据不表示无风险。</Typography.Paragraph></Card>}
      <Card className="section-gap" title="逐阶段记录"><StageTable stages={local.scan.stages} /></Card>
    </>}
  </div>;
}
