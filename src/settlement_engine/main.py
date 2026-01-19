import logging
import os
import redis
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from src.settlement_engine.api.v1 import transactions
from src.settlement_engine.services.intake_service import IntakeService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application Lifecycle Manager.
    1. Connects to Redis
    2. Initializes IntakeService (Kafka)
    3. Injects service into the app state for the router to use
    """
    logger.info("Settlement Engine starting up...")

    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    kafka_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092").split(",")

    redis_client = None
    intake_service = None

    try:
        redis_client = redis.Redis(
            host=redis_host, 
            port=redis_port, 
            db=0, 
            decode_responses=True 
        )
        redis_client.ping() 
        logger.info(f"Connected to Redis at {redis_host}:{redis_port}")

        intake_service = IntakeService(
            redis_client=redis_client,
            kafka_bootstrap_servers=kafka_servers
        )
        
        app.state.intake_service = intake_service

    except Exception as e:
        logger.error(f"Critical Startup Failure: {e}")
        raise e

    yield

    logger.info("Settlement Engine shutting down...")
    if intake_service:
        intake_service.shutdown()
    if redis_client:
        redis_client.close()

app = FastAPI(
    title="Settlement Engine API",
    version="1.0.0",
    description="Real-Time Transaction Intake & Settlement",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    transactions.router, 
    prefix="/api/v1/transactions", 
    tags=["transactions"]
)

@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {
        "status": "healthy", 
        "service": "settlement-engine",
        "version": "1.0.0"
    }