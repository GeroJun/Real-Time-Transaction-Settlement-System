import json
import hashlib
import logging
from typing import Optional
import redis
from kafka import KafkaProducer
from kafka.errors import KafkaError

# Import your models
from src.settlement_engine.models import TransactionRequest, TransactionResponse, TransactionStatus

logger = logging.getLogger(__name__)

class IntakeService:
    """
    Handles transaction intake, deduplication, and routing.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        kafka_bootstrap_servers: list,
        dedup_ttl_seconds: int = 86400  # 24 hours
    ):
        self.redis = redis_client
        self.dedup_ttl = dedup_ttl_seconds
        
        # Initialize Kafka Producer
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8'),
                acks='all',
                retries=3,
                compression_type='gzip' 
            )
            logger.info(f"Connected to Kafka: {kafka_bootstrap_servers}")
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            raise

    async def process_transaction(self, request: TransactionRequest) -> TransactionResponse:
        """
        Main entry point: Validates, Dedups, and Publishes.
        """
        self._validate_transaction(request)

        # Check Deduplication (Idempotency)
        cached_response = self._check_duplicate(request.idempotency_key)
        if cached_response:
            logger.info(f"Duplicate detected: {request.transaction_id}")
            cached_response.status = TransactionStatus.DEDUPED
            return cached_response

        # Create Response Object
        response = TransactionResponse(
            transaction_id=request.transaction_id,
            status=TransactionStatus.SUBMITTED,
            message="Transaction queued for processing"
        )

        # Store Idempotency Key (Redis)
        self._store_idempotency_key(request.idempotency_key, response)

        # Publish to Kafka
        await self._publish_to_kafka(
            topic="transactions.intake",
            transaction=response.dict()
        )
        
        return response

    def _validate_transaction(self, request: TransactionRequest):
        """Run business validation rules."""
        if request.amount <= 0:
            raise ValueError("Amount must be positive")
        
        if request.source_currency == request.destination_currency:
             pass

    def _check_duplicate(self, idempotency_key: str) -> Optional[TransactionResponse]:
        """Check Redis for existing key."""
        key = f"dedup:{idempotency_key}"
        data = self.redis.get(key)
        if data:
            return TransactionResponse(**json.loads(data))
        return None

    def _store_idempotency_key(self, idempotency_key: str, response: TransactionResponse):
        """Save result to Redis."""
        key = f"dedup:{idempotency_key}"
        self.redis.setex(
            key, 
            self.dedup_ttl, 
            json.dumps(response.dict(), default=str)
        )

    async def _publish_to_kafka(self, topic: str, transaction: dict):
        """Send to Kafka."""
        try:
            key = transaction['transaction_id'].encode('utf-8')
            self.producer.send(topic, value=transaction, key=key)
            self.producer.flush() 
        except KafkaError as e:
            logger.error(f"Kafka Publish Error: {e}")
            raise