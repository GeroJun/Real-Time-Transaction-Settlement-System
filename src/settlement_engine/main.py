"""FastAPI application for settlement engine."""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

import redis
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .models import (
    TransactionRequest,
    TransactionResponse,
    TransactionStatus,
    BatchStatus,
    HealthCheckResponse,
    MetricsSnapshot,
    CounterpartyExposure,
    LiquidityForecast
)
from .services.intake_service import IntakeService
from .services.batching_service import BatchingService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Global service instances
intake_service: Optional[IntakeService] = None
batching_service: Optional[BatchingService] = None
redis_client: Optional[redis.Redis] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    # Startup
    logger.info("Settlement Engine starting up...")
    
    global intake_service, batching_service, redis_client
    
    # Initialize Redis
    try:
        redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=0,
            decode_responses=True
        )
        redis_client.ping()
        logger.info("Connected to Redis")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise
    
    # Initialize services
    try:
        kafka_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092').split(',')
        intake_service = IntakeService(
            redis_client=redis_client,
            kafka_bootstrap_servers=kafka_servers
        )
        logger.info("Intake service initialized")
        
        batching_service = BatchingService()
        logger.info("Batching service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise
    
    logger.info("Settlement Engine started successfully")
    yield
    
    # Shutdown
    logger.info("Settlement Engine shutting down...")
    if intake_service:
        intake_service.shutdown()
    logger.info("Settlement Engine shut down gracefully")


app = FastAPI(
    title="Real-Time Transaction Settlement System",
    description="Production-grade settlement engine with smart batching and consensus",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Transaction Endpoints
# ============================================================================

@app.post("/api/v1/transactions", response_model=TransactionResponse)
async def submit_transaction(request: TransactionRequest) -> TransactionResponse:
    """Submit a transaction for settlement.
    
    Request Body:
        - transaction_id: Unique transaction identifier
        - amount: Transaction amount (decimal, positive)
        - source_currency: ISO 4217 source currency
        - destination_currency: ISO 4217 destination currency
        - source_account: Source account identifier
        - destination_account: Destination account identifier
        - counterparty_id: Settlement counterparty
        - idempotency_key: Idempotency key for deduplication
        - settlement_window: Optional settlement timing (default: RTGS)
    
    Returns:
        TransactionResponse with transaction_id and initial status
    
    Raises:
        HTTPException: 400 if validation fails, 409 if duplicate
    """
    if not intake_service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    try:
        response, is_duplicate = await intake_service.submit_transaction(request)
        
        status_code = 409 if is_duplicate else 201
        return JSONResponse(
            status_code=status_code,
            content=response.dict()
        )
    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except ValidationError as e:
        logger.warning(f"Schema validation error: {e}")
        raise HTTPException(status_code=400, detail="Invalid request schema")
    except Exception as e:
        logger.error(f"Unexpected error submitting transaction: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/transactions/{transaction_id}", response_model=Optional[TransactionResponse])
async def get_transaction(transaction_id: str) -> Optional[TransactionResponse]:
    """Retrieve transaction by ID.
    
    Args:
        transaction_id: Transaction identifier
    
    Returns:
        Transaction details or None if not found
    """
    if not intake_service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    try:
        status = intake_service.get_transaction_status(transaction_id)
        if not status:
            raise HTTPException(status_code=404, detail="Transaction not found")
        return status
    except Exception as e:
        logger.error(f"Error retrieving transaction: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Settlement Batch Endpoints
# ============================================================================

@app.get("/api/v1/settlements/{batch_id}/status")
async def get_batch_status(batch_id: str) -> dict:
    """Retrieve settlement batch status.
    
    Args:
        batch_id: Batch identifier
    
    Returns:
        Batch status details
    """
    # TODO: Implement batch status retrieval from database
    return {
        "batch_id": batch_id,
        "status": BatchStatus.CREATED.value,
        "transactions_count": 0,
        "created_at": datetime.utcnow().isoformat()
    }


@app.post("/api/v1/settlements/{batch_id}/confirm")
async def confirm_settlement(batch_id: str) -> dict:
    """Confirm settlement execution.
    
    Args:
        batch_id: Batch identifier to confirm
    
    Returns:
        Confirmation details
    """
    # TODO: Implement settlement confirmation logic
    return {
        "batch_id": batch_id,
        "confirmed_at": datetime.utcnow().isoformat(),
        "status": "confirmed"
    }


# ============================================================================
# Liquidity & Risk Endpoints
# ============================================================================

@app.get("/api/v1/liquidity/forecast", response_model=Optional[LiquidityForecast])
async def get_liquidity_forecast(
    currency: str = Query(..., regex=r"^[A-Z]{3}$"),
    days_ahead: int = Query(7, ge=1, le=30)
) -> Optional[LiquidityForecast]:
    """Get liquidity forecast for a currency.
    
    Args:
        currency: ISO 4217 currency code
        days_ahead: Number of days to forecast (1-30)
    
    Returns:
        Liquidity forecast or None
    """
    # TODO: Implement liquidity forecasting
    return LiquidityForecast(
        currency=currency,
        forecast_date=datetime.utcnow(),
        forecasted_outflows=Decimal('1000000.00'),
        forecasted_inflows=Decimal('1100000.00'),
        net_position=Decimal('100000.00'),
        confidence_interval_lower=Decimal('950000.00'),
        confidence_interval_upper=Decimal('1150000.00'),
        recommendations=["Monitor EUR/USD volatility", "Pre-position funds on Tuesday"]
    )


@app.get("/api/v1/risk/counterparties", response_model=List[CounterpartyExposure])
async def get_counterparty_exposure() -> List[CounterpartyExposure]:
    """Get real-time counterparty exposure.
    
    Returns:
        List of counterparty exposures
    """
    # TODO: Implement counterparty risk monitoring
    return [
        CounterpartyExposure(
            counterparty_id="counterparty_bank_a",
            total_exposure_usd=Decimal('10000000.00'),
            pending_settlements=5,
            pending_amount_usd=Decimal('2000000.00'),
            max_exposure_limit_usd=Decimal('50000000.00'),
            utilization_percentage=20.0,
            credit_rating="AA",
            risk_level="low"
        )
    ]


# ============================================================================
# Monitoring & Health Endpoints
# ============================================================================

@app.get("/api/v1/health", response_model=HealthCheckResponse)
async def health_check() -> HealthCheckResponse:
    """Check system health.
    
    Returns:
        Health status
    """
    # TODO: Implement actual health checks
    return HealthCheckResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        kafka_status="healthy",
        database_status="healthy",
        redis_status="healthy" if redis_client else "unhealthy",
        consensus_status="healthy",
        pending_transactions=0,
        pending_batches=0,
        version="1.0.0"
    )


@app.get("/api/v1/metrics", response_model=MetricsSnapshot)
async def get_metrics() -> MetricsSnapshot:
    """Get current system metrics.
    
    Returns:
        Metrics snapshot
    """
    # TODO: Implement actual metrics collection
    return MetricsSnapshot(
        timestamp=datetime.utcnow(),
        throughput_tps=1000.5,
        average_latency_ms=25.3,
        p99_latency_ms=95.2,
        p999_latency_ms=150.0,
        total_transactions_processed=50000,
        total_amount_settled_usd=Decimal('500000000.00'),
        failed_settlements=2,
        consensus_rounds_completed=150,
        active_batches=10
    )


# ============================================================================
# Root Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Real-Time Transaction Settlement System",
        "version": "1.0.0",
        "status": "running",
        "documentation": "/docs"
    }


@app.get("/docs")
async def docs():
    """API documentation endpoint."""
    return {
        "message": "API documentation available at /docs (Swagger UI)",
        "endpoints": {
            "transactions": "/api/v1/transactions",
            "settlements": "/api/v1/settlements",
            "liquidity": "/api/v1/liquidity/forecast",
            "risk": "/api/v1/risk/counterparties",
            "health": "/api/v1/health",
            "metrics": "/api/v1/metrics"
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv('PORT', 8000)),
        workers=int(os.getenv('WORKERS', 4))
    )
