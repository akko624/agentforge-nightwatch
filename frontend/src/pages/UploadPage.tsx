import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Checkbox, Input, Radio, Space, Typography, Upload } from 'antd';
import { InboxOutlined, LockOutlined } from '@ant-design/icons';
import { Link, useNavigate } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import { ErrorNotice } from '../components/shared';
import type { UploadResult } from '../types';

const MAX_UPLOAD = 20 * 1024 * 1024;
export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null); const [owner, setOwner] = useState('');
  const [mode, setMode] = useState('standard'); const [force, setForce] = useState(false); const [validation, setValidation] = useState('');
  const [imported, setImported] = useState<UploadResult | null>(null);
  const navigate = useNavigate(); const cache = useQueryClient();
  const mutation = useMutation({ mutationFn: async () => {
    if (!file) throw new Error('请先选择 ZIP 文件');
    const artifact = imported ?? await api.upload(file, owner); setImported(artifact);
    return api.createScan(artifact.version_id, mode === 'standard' ? ['schema', 'static', 'quality'] : ['schema', 'static', 'quality', 'dependencies', 'semantic', 'dynamic'], force);
  }, onSuccess: async (scan) => { await cache.invalidateQueries({ queryKey: ['scans'] }); navigate(`/scans/${scan.scan_id}`); } });
  const setArchive = (next: File) => {
    mutation.reset(); setImported(null);
    if (!next.name.toLowerCase().endsWith('.zip')) { setValidation('仅支持 .zip 文件。'); setFile(null); return false; }
    if (next.size > MAX_UPLOAD) { setValidation('压缩包超过 20 MiB 限制。'); setFile(null); return false; }
    setValidation(''); setFile(next); return false;
  };
  return <>
    <Link to="/" className="back-link">← 返回扫描工作台</Link>
    <Typography.Text className="eyebrow">ARTIFACT INTAKE / SKILL TRACK</Typography.Text><Typography.Title level={1}>导入首个支持的 Agent 工件</Typography.Title>
    <Typography.Paragraph type="secondary">当前工件类型为 Skill ZIP。上传后服务端安全检查文件与结构，再交由独立 Worker 运行静态分析；工作流、提示包和连接器类型尚在路线图中。</Typography.Paragraph>
    <div className="upload-grid"><Card title="上传工件">
      <Upload.Dragger accept=".zip" multiple={false} maxCount={1} disabled={mutation.isPending} beforeUpload={setArchive} fileList={file ? [{ uid: 'selected', name: file.name, status: 'done', size: file.size }] : []} onRemove={() => { setFile(null); setImported(null); mutation.reset(); return true; }}>
        <p className="ant-upload-drag-icon"><InboxOutlined /></p><p className="ant-upload-text">拖入 ZIP 或点击选择文件</p><p className="ant-upload-hint">最多 20 MiB · 一个 Skill 根目录 · 必须包含 SKILL.md</p>
      </Upload.Dragger>
      {validation && <Alert className="section-gap" showIcon type="error" message={validation} />}
      <label className="field-label" htmlFor="owner-label">作者标签（可选，非可信身份）</label><Input id="owner-label" placeholder="例如：example-team" value={owner} maxLength={100} disabled={mutation.isPending} onChange={(event) => { setOwner(event.target.value); setImported(null); mutation.reset(); }} />
      <div className="field-label">检测模式</div><Radio.Group value={mode} disabled={mutation.isPending} onChange={(event) => setMode(event.target.value)}><Space direction="vertical"><Radio value="standard">静态 MVP：规范、安全规则、局部质量</Radio><Radio value="extended">请求全部阶段（扩展能力当前不可用）</Radio></Space></Radio.Group>
      <Typography.Paragraph type="secondary" className="section-gap">规范与静态安全为必需检查。请求未配置的依赖漏洞、语义或动态能力时，报告会标记 NOT_RUN / UNAVAILABLE，并由门禁判断证据是否充分。</Typography.Paragraph>
      <Checkbox checked={force} disabled={mutation.isPending} onChange={(event) => setForce(event.target.checked)}>强制新建扫描（相同内容默认复用相同配置的已有任务）</Checkbox>
      {imported && <Alert className="section-gap" type="info" message="工件已安全导入" description={<span>内容 SHA256：<code className="hash">{imported.sha256}</code>。若创建任务失败，可直接重试。</span>} />}
      <ErrorNotice error={mutation.error} title="导入或创建扫描失败" />
      {mutation.error instanceof ApiError && typeof mutation.error.details?.scan_id === 'string' && <Link to={`/scans/${mutation.error.details.scan_id}`}>查看已记录的失败扫描</Link>}
      <Button className="submit-button" type="primary" size="large" block loading={mutation.isPending} disabled={!file || !!validation} onClick={() => mutation.mutate()}>{mutation.isPending ? '正在安全导入并创建任务…' : imported ? '重试创建扫描' : '上传并创建扫描'}</Button>
    </Card><aside><Card title={<Space><LockOutlined />导入与执行边界</Space>}><ul className="guidance-list"><li>ZIP 根目录直接包含 SKILL.md，或只有一个 Skill 子目录。</li><li>拒绝路径穿越、绝对路径、链接、设备文件和危险压缩包。</li><li>最多 300 个条目、100 MiB 解压体积、10 MiB 单文件、10 层路径、100:1 压缩比。</li><li>作者权限声明是请求与承诺，不会自动授权。</li><li>未受信 Skill 不会在 API、Worker 或开发主机上执行。</li></ul><Alert showIcon type="warning" message="动态沙箱与模型宿主尚未接入" description="平台会真实报告缺失能力，不会使用本机命令执行替代隔离环境。" /></Card></aside></div>
  </>;
}
