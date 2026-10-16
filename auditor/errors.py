"""Safe error types; raw upstream errors never reach logs."""


class AuditError(Exception):
    """Fatal audit failure."""


class ToolError(AuditError):
    """Recoverable inspection failure."""


class ReportError(AuditError):
    """Unsupported or invalid report; the agent may repair it."""


class ContextLimitError(AuditError):
    """Provider rejected the accumulated request size; host may compact observations."""
