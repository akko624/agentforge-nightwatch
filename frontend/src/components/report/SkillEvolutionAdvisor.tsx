import { BulbOutlined, DownloadOutlined, ExperimentOutlined, RocketOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Space, Tag, Typography } from 'antd';
import type { FullReport, ScanSummary } from '../../types';
import './evolution.css';

type Priority = 'P0' | 'P1' | 'P2';
interface ImprovementAction { priority: Priority; title: string; evidence: string; next: string; kind: 'security' | 'quality' | 'coverage' | 'delivery' }

const actionStyle: Record<ImprovementAction['kind'], { icon: typeof SafetyCertificateOutlined; label: string }> = {
  security: { icon: SafetyCertificateOutlined, label: '安全整改' },
  quality: { icon: BulbOutlined, label: 'Skill 体验' },
  coverage: { icon: ExperimentOutlined, label: '评测证据' },
  delivery: { icon: RocketOutlined, label: '交付与推广' },
};

function actionPriority(scan: ScanSummary, report: FullReport): ImprovementAction[] {
  const count = (severity: string) => report.security.finding_counts[severity.toLowerCase()] ?? 0;
  const criticalHigh = count('CRITICAL') + count('HIGH');
  const staticStage = scan.stages.static;
  const dependencies = scan.stages.dependencies;
  const dynamic = scan.stages.dynamic;
  const docsSignals = report.security.findings.filter((finding) => ['SQSP-S015', 'SQSP-S016', 'S015', 'S016'].includes(finding.rule_id)).length;
  const actions: ImprovementAction[] = [];
  if (criticalHigh > 0) actions.push({ priority: 'P0', kind: 'security', title: '先关闭严重与高风险证据链', evidence: `本次静态检查有 ${criticalHigh} 条严重/高风险候选；发布决策为 ${scan.release_decision}。`, next: '逐条查看证据与整改建议；修复后重新扫描，并保留版本对比。不要把规则命中直接等同于恶意。' });
  if (staticStage?.status === 'PARTIAL' || staticStage?.status === 'ERROR' || staticStage?.status === 'TIMEOUT') actions.push({ priority: 'P0', kind: 'coverage', title: '先补齐静态扫描的可解释覆盖', evidence: `静态阶段状态为 ${staticStage.status}，当前结果不能代表完整静态覆盖。`, next: '检查不支持载荷、解析错误与规则盲区；将可验证样例加入回归集，而不是将未测部分标为通过。' });
  if (report.quality.coverage < 1 || report.quality.score === null) actions.push({ priority: 'P1', kind: 'coverage', title: '为关键任务补充真实评测用例', evidence: `质量覆盖为 ${Math.round(report.quality.coverage * 100)}%，完整质量分${report.quality.score === null ? '尚未评测' : `为 ${report.quality.score.toFixed(1)}`}。`, next: '定义输入、预期输出、失败边界和稳定性阈值；接入获批准的真实宿主或隔离 Runner 后再记录正确性与可靠性。' });
  if (dynamic && ['UNAVAILABLE', 'NOT_RUN', 'PARTIAL'].includes(dynamic.status)) actions.push({ priority: 'P1', kind: 'security', title: '把动态验证作为受控能力建设', evidence: `动态阶段为 ${dynamic.status}，平台没有执行上传代码。`, next: '设计最小权限、可销毁、无宿主凭据的隔离运行环境；在此之前不要用开发机 subprocess 或普通容器替代。' });
  if (dependencies && ['NOT_RUN', 'PARTIAL', 'UNAVAILABLE'].includes(dependencies.status)) actions.push({ priority: 'P1', kind: 'coverage', title: '建立依赖锁定与漏洞情报闭环', evidence: `依赖阶段为 ${dependencies.status}，不能将此解释为“没有已知漏洞”。`, next: '补齐锁文件、固定来源与版本；接入可审计的漏洞数据源后，记录数据版本、命中时间和不可用状态。' });
  if (docsSignals > 0 || report.quality.static_subscore !== null && report.quality.static_subscore < 80) actions.push({ priority: 'P2', kind: 'quality', title: '提升 Skill 的可执行说明与失败处理', evidence: `${docsSignals ? `检测到 ${docsSignals} 条维护性信号；` : ''}局部静态质量为 ${report.quality.static_subscore?.toFixed(1) ?? '未评测'}。`, next: '为输入、输出、权限、外部工具失败、用户确认与回滚写出明确行为；补充版本、许可证与可重复测试。' });
  actions.push({ priority: 'P2', kind: 'delivery', title: '把可复核结果转化为可分享交付物', evidence: '报告可导出为完整 JSON，也可生成允许字段的聚合静态摘要。', next: '内部评审保留完整证据；对外只发布复核后的聚合看板。不要把原 ZIP、路径、hash 或完整报告放到公共链接。' });
  return actions;
}

export function buildSkillImprovementBrief(report: FullReport, scan: ScanSummary): string {
  const actions = actionPriority(scan, report);
  const lines = [
    '# SkillForge NightWatch · Skill 改进简报', '',
    '## 本次事实',
    `- 扫描状态：${scan.status}`, `- 发布决策：${scan.release_decision}`, `- 安全结论：${scan.security_verdict}`, `- 风险发现：${report.security.findings.length} 条（严重 ${report.security.finding_counts.critical ?? 0}，高风险 ${report.security.finding_counts.high ?? 0}）`,
    `- 质量覆盖：${Math.round(report.quality.coverage * 100)}%`, `- 完整质量分：${report.quality.score === null ? '未评测' : report.quality.score.toFixed(1)}`, '',
    '## 改进优先级',
    ...actions.flatMap((action) => [`### ${action.priority} · ${action.title}`, `- 依据：${action.evidence}`, `- 下一步：${action.next}`, '']),
    '## 使用边界',
    '- 本简报只根据已记录的扫描结果生成，不是自动修复、模型评测或安全认证。',
    '- 不要执行待测 Skill 来验证建议；动态和真实宿主评测必须使用获批准的隔离环境。',
    '- 此文件可能包含内部风险统计，应按原报告的访问范围处理。', '',
  ];
  return lines.join('\n');
}

function downloadBrief(text: string) {
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob); const anchor = document.createElement('a');
  anchor.href = url; anchor.download = 'skillforge-improvement-brief.md'; document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
}

export function SkillEvolutionAdvisor({ report, scan }: { report: FullReport; scan: ScanSummary }) {
  const actions = actionPriority(scan, report); const brief = buildSkillImprovementBrief(report, scan);
  return <div className="evolution-workbench">
    <div className="evolution-head"><div><Typography.Text className="eyebrow">SKILL EVOLUTION WORKBENCH</Typography.Text><Typography.Title level={3}>把扫描结论变成下一轮可验证的改进。</Typography.Title><Typography.Paragraph type="secondary">建议完全来自本次已测事实，不会自动改写 Skill、调用模型或执行待测内容。导出的 Markdown 可交给团队或其他 Agent 继续拆解。</Typography.Paragraph></div><Button aria-label="导出改进简报" type="primary" icon={<DownloadOutlined />} onClick={() => downloadBrief(brief)}>导出改进简报</Button></div>
    <Alert showIcon type="info" message="建议是整改路线，不是自动修复" description="高风险证据优先于体验优化；未运行的动态、依赖和真实宿主能力会被明确保留为证据缺口。" />
    <div className="evolution-actions">{actions.map((action) => { const style = actionStyle[action.kind]; const Icon = style.icon; return <Card className={`evolution-action evolution-${action.priority.toLowerCase()}`} size="small" key={`${action.priority}-${action.title}`}><div className="evolution-action-top"><Space size={8}><span className="evolution-action-icon"><Icon /></span><Tag>{action.priority}</Tag><Typography.Text type="secondary">{style.label}</Typography.Text></Space></div><Typography.Title level={5}>{action.title}</Typography.Title><p><strong>依据：</strong>{action.evidence}</p><p><strong>下一步：</strong>{action.next}</p></Card>; })}</div>
    <div className="evolution-roadmap"><div><span>COMPETITION-READY BACKLOG</span><h4>下一步可演示的能力</h4></div><div className="evolution-roadmap-items"><p><Tag color="blue">待实现</Tag><strong>补丁审阅台</strong>：让 Agent 输出候选 diff、规则命中解释与人工批准点，绝不自动写回 Skill。</p><p><Tag color="purple">待实现</Tag><strong>评测用例工厂</strong>：把任务目标转成可审计的输入/预期输出/失败边界，再交给真实隔离 Runner。</p><p><Tag color="gold">待实现</Tag><strong>Night Batch</strong>：低峰批量扫描、预算与队列可视化；适合强调算力编排，而非为了演示而执行不可信代码。</p></div></div>
  </div>;
}
