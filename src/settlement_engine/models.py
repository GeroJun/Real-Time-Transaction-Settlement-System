"""Pydantic models for settlement engine."""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator
from uuid import UUID


class TransactionStatus(str, Enum):
    """Transaction settlement status."""
    SUBMITTED = "submitted"
    DEDUPED = "deduped"
    BATCHED = "batched"
    CONSENSUS_PENDING = "consensus_pending"
    CONSENSUS_APPROVED = "consensus_approved"
    SETTLEMENT_PENDING = "settlement_pending"
    SETTLED = "settled"
    FAILED = "failed"
    REVERSED = "reversed"


class BatchStatus(str, Enum):
    """Settlement batch status."""
    CREATED = "created"
    OPTIMIZED = "optimized"
    SUBMITTED_TO_CONSENSUS = "submitted_to_consensus"
    CONSENSUS_ACHIEVED = "consensus_achieved"
    SETTLEMENT_INITIATED = "settlement_initiated"
    SETTLED = "settled"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"


class SettlementWindow(str, Enum):
    """Settlement timing windows."""
    RTGS = "rtgs"  # Real-Time Gross Settlement (immediate)
    T0 = "t0"      # Same-day settlement
    T1 = "t1"      # Next-day settlement
    T2 = "t2"      # T+2 settlement


class TransactionRequest(BaseModel):
    """Incoming transaction for settlement."""
    transaction_id: str = Field(..., min_length=1, max_length=50)
    amount: Decimal = Field(..., gt=0)
    source_currency: str = Field(..., pattern=r"^[A-Z]{3}$")
    destination_currency: str = Field(..., pattern=r"^[A-Z]{3}$")
    source_account: str = Field(..., min_length=1, max_length=50)
    destination_account: str = Field(..., min_length=1, max_length=50)
    counterparty_id: str = Field(..., min_length=1, max_length=50)
    idempotency_key: str = Field(..., min_length=1, max_length=100)
    settlement_window: SettlementWindow = SettlementWindow.RTGS
    metadata: Optional[dict] = Field(default_factory=dict)

    @field_validator('source_currency', 'destination_currency')
    @classmethod
    def validate_currency(cls, v):
        """Validate ISO 4217 currency codes."""
        valid_currencies = {
            'USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD', 'NZD',
            'CNY', 'INR', 'KRW', 'SGD', 'HKD', 'MXN', 'BRL', 'ZAR'
        }
        if v not in valid_currencies:
            raise ValueError(f'Unsupported currency: {v}')
        return v

    @field_validator('transaction_id')
    @classmethod
    def validate_transaction_id(cls, v):
        """Ensure transaction ID follows naming conventions."""
        if not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('Transaction ID must be alphanumeric')
        return v


class TransactionResponse(TransactionRequest):
    """Transaction response with tracking info."""
    status: TransactionStatus = TransactionStatus.SUBMITTED
    batch_id: Optional[str] = None
    settlement_time: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    fx_rate: Optional[Decimal] = None  # Source to destination rate
    settlement_fee: Optional[Decimal] = None


class SettlementBatch(BaseModel):
    """Optimized settlement batch."""
    batch_id: str = Field(..., min_length=1, max_length=50)
    status: BatchStatus = BatchStatus.CREATED
    transactions: List[str] = Field(default_factory=list)  # Transaction IDs
    total_amount_usd: Decimal = Field(default=Decimal('0'))
    optimization_cost_saved: Decimal = Field(default=Decimal('0'))
    currency_pairs: List[tuple] = Field(default_factory=list)  # [(USD, EUR), ...]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    settled_at: Optional[datetime] = None
    consensus_round: Optional[int] = None


class SettlementInstruction(BaseModel):
    """Instruction for fund movement."""
    instruction_id: str
    batch_id: str
    source_account: str
    destination_account: str
    amount: Decimal
    currency: str
    settlement_window: SettlementWindow
    counterparty_id: str
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = Field(default_factory=datetime.utcnow)
    executed_at: Optional[datetime] = None
    wire_id: Optional[str] = None  # Bank wire reference


class SettlementLedgerEntry(BaseModel):
    """Immutable ledger entry (event sourcing)."""
    entry_id: str
    transaction_id: str
    batch_id: str
    event_type: str  # "SUBMITTED", "BATCHED", "CONSENSUS_ACHIEVED", "SETTLED"
    amount: Decimal
    currency: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    actor: str  # Service that performed action
    details: dict = Field(default_factory=dict)


class LiquidityForecast(BaseModel):
    """Liquidity forecast for settlement planning."""
    currency: str
    forecast_date: datetime
    forecasted_outflows: Decimal  # USD equivalent
    forecasted_inflows: Decimal
    net_position: Decimal
    confidence_interval_lower: Decimal
    confidence_interval_upper: Decimal
    recommendations: List[str] = Field(default_factory=list)


class CounterpartyExposure(BaseModel):
    """Real-time counterparty risk exposure."""
    counterparty_id: str
    total_exposure_usd: Decimal
    pending_settlements: int
    pending_amount_usd: Decimal
    max_exposure_limit_usd: Optional[Decimal] = None
    utilization_percentage: Optional[float] = None
    credit_rating: Optional[str] = None
    last_settlement: Optional[datetime] = None
    risk_level: str = "low"  # low, medium, high, critical


class BatchOptimizationResult(BaseModel):
    """Result of batching optimization."""
    batch_id: str
    transactions: List[str]
    optimization_metrics: dict  # Detailed metrics
    total_cost_before_optimization: Decimal
    total_cost_after_optimization: Decimal
    cost_savings: Decimal
    cost_savings_percentage: float
    settlement_window: SettlementWindow
    netting_details: dict  # Multilateral netting info


class HealthCheckResponse(BaseModel):
    """System health check response."""
    status: str  # "healthy", "degraded", "unhealthy"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    kafka_status: str
    database_status: str
    redis_status: str
    consensus_status: str
    pending_transactions: int
    pending_batches: int
    version: str = "1.0.0"


class MetricsSnapshot(BaseModel):
    """Real-time metrics snapshot."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    throughput_tps: float  # Transactions per second
    average_latency_ms: float
    p99_latency_ms: float
    p999_latency_ms: float
    total_transactions_processed: int
    total_amount_settled_usd: Decimal
    failed_settlements: int
    consensus_rounds_completed: int
    active_batches: int
