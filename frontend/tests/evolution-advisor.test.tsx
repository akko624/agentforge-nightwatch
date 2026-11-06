import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { SkillEvolutionAdvisor, buildSkillImprovementBrief } from '../src/components/report/SkillEvolutionAdvisor';
import { finding, report, scan } from './fixtures';

afterEach(cleanup);

describe('skill evolution workbench', () => {
  it('turns measured evidence into a bounded improvement brief without copying evidence excerpts', () => {
    const brief = buildSkillImprovementBrief(report, scan);
    expect(brief).toContain('先关闭严重与高风险证据链');
    expect(brief).toContain('把动态验证作为受控能力建设');
    expect(brief).toContain('完整质量分：未评测');
    expect(brief).toContain('不是自动修复、模型评测或安全认证');
    expect(brief).not.toContain(finding.evidence_excerpt!);
  });

  it('shows a real export action and marks future capability ideas as unimplemented', () => {
    render(<SkillEvolutionAdvisor report={report} scan={scan} />);
    expect(screen.getByRole('button', { name: '导出改进简报' })).toBeInTheDocument();
    expect(screen.getByText('补丁审阅台')).toBeInTheDocument();
    expect(screen.getAllByText('待实现')).toHaveLength(3);
    expect(screen.getByText('建议是整改路线，不是自动修复')).toBeInTheDocument();
  });
});
