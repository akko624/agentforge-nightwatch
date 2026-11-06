from backend.app.scan.contracts import (
    AnalysisResult,
    CapabilityReport,
    SandboxCaseRequest,
    SandboxCaseResult,
    ScanContext,
)


class DisabledSandboxRunner:
    def capability(self) -> CapabilityReport:
        return CapabilityReport(reason="No approved isolated sandbox configured; Skill code is never executed")

    def run_case(self, request: SandboxCaseRequest) -> SandboxCaseResult:
        return SandboxCaseResult(status="UNAVAILABLE", reason=self.capability().reason)


class NoopAnalyzer:
    def analyze(self, context: ScanContext) -> AnalysisResult:
        return AnalysisResult(status="UNAVAILABLE", reason="No approved semantic model configured")


class DisabledQualityRunner:
    def capability(self) -> CapabilityReport:
        return CapabilityReport(reason="No observable real Skill host configured")

    def evaluate(self, context: ScanContext, cases: list[dict]) -> AnalysisResult:
        return AnalysisResult(status="NOT_RUN", reason=self.capability().reason)


class DisabledExternalAdapter:
    def __init__(self, name: str):
        self.name = name

    def analyze(self, context: ScanContext) -> AnalysisResult:
        return AnalysisResult(status="UNAVAILABLE", reason=f"{self.name}: version and output contract not configured")


class CiscoScannerAdapter(DisabledExternalAdapter):
    def __init__(self):
        super().__init__("cisco-scanner")


class SkillSpectorAdapter(DisabledExternalAdapter):
    def __init__(self):
        super().__init__("skillspector")


class OSVAdapter(DisabledExternalAdapter):
    def __init__(self):
        super().__init__("osv-scanner")
