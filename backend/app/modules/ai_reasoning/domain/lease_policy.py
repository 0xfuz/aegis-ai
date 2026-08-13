"""Central, trusted-time lease policy for asynchronous intelligence execution."""
from dataclasses import dataclass

@dataclass(frozen=True)
class IntelligenceLeasePolicy:
    version: str = "intelligence-lease-v1"
    lease_seconds: int = 60
    heartbeat_seconds: int = 20
    max_execution_attempts: int = 3
    recovery_batch_size: int = 100
    queued_reconciliation_batch_size: int = 100

    def __post_init__(self) -> None:
        if self.lease_seconds <= 0 or self.heartbeat_seconds <= 0 or self.heartbeat_seconds >= self.lease_seconds:
            raise ValueError("Lease duration must be positive and exceed heartbeat interval.")
        if self.max_execution_attempts <= 0:
            raise ValueError("Maximum execution attempts must be positive.")
        if not 1 <= self.recovery_batch_size <= 1000 or not 1 <= self.queued_reconciliation_batch_size <= 1000:
            raise ValueError("Lease batch sizes must be between 1 and 1000.")
