"""Transaction intake and deduplication service."""

import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Tuple
from uuid import uuid4
import logging

import redis
from kafka import KafkaProducer
from kafka.errors import KafkaError

from ..models import TransactionRequest, TransactionResponse, TransactionStatus

logger = logging.getLogger(__name__)


class IntakeService:
    """Handles transaction intake, deduplication, and routing.
    
    This service:
    1. Validates incoming transactions
    2. Deduplicates using idempotency keys (Redis)
    3. Routes to Kafka for processing
    4. Tracks transaction status
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        kafka_bootstrap_servers: list,
        dedup_ttl_seconds: int = 86400  # 24 hours
    ):
        """Initialize intake service.
        
        Args:
            redis_client: Redis client for idempotency
            kafka_bootstrap_servers: Kafka bootstrap servers
            dedup_ttl_seconds: Time-to-live for dedup keys
        """
        self.redis = redis_client
        self.dedup_ttl = dedup_ttl_seconds
        
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(
                    v,
                    default=str
                ).encode('utf-8'),
                acks='all',  # Wait for all replicas
                retries=3,
                compression_type='snappy'
            )
            logger.info(f"Connected to Kafka: {kafka_bootstrap_servers}")
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            raise

    async def submit_transaction(
        self,
        transaction_request: TransactionRequest
    ) -> Tuple[TransactionResponse, bool]:
        """Submit transaction for settlement.
        
        Args:
            transaction_request: Incoming transaction
            
        Returns:
            Tuple of (TransactionResponse, is_duplicate)
            
        Raises:
            ValueError: If transaction validation fails
        """
        # Validate transaction
        self._validate_transaction(transaction_request)
        
        # Check for duplicate using idempotency key
        existing_txn = self._check_duplicate(
            transaction_request.idempotency_key
        )
        if existing_txn:
            logger.info(
                f"Duplicate detected: {transaction_request.transaction_id}"
            )
            return existing_txn, True
        
        # Create transaction response
        transaction_response = TransactionResponse(
            **transaction_request.dict(),
            status=TransactionStatus.SUBMITTED
        )
        
        # Store for deduplication
        self._store_idempotency_key(
            transaction_request.idempotency_key,
            transaction_response
        )
        
        # Publish to Kafka
        try:
            await self._publish_to_kafka(
                topic="transactions.intake",
                transaction=transaction_response.dict()
            )
            logger.info(
                f"Transaction submitted: {transaction_response.transaction_id}"
            )
        except Exception as e:
            logger.error(f"Failed to publish transaction: {e}")
            raise
        
        return transaction_response, False

    def _validate_transaction(self, transaction: TransactionRequest) -> None:
        """Validate transaction data.
        
        Args:
            transaction: Transaction to validate
            
        Raises:
            ValueError: If validation fails
        """
        # Amount validation
        if transaction.amount <= 0:
            raise ValueError("Amount must be greater than 0")
        
        if transaction.amount > Decimal('999999999.99'):
            raise ValueError("Amount exceeds maximum limit")
        
        # Account validation
        if transaction.source_account == transaction.destination_account:
            raise ValueError("Source and destination accounts cannot be same")
        
        if transaction.source_currency == transaction.destination_currency:
            # For same-currency transactions, FX rate is 1.0
            pass
        
        # Counterparty validation
        if not transaction.counterparty_id or \
           transaction.counterparty_id.strip() == "":
            raise ValueError("Counterparty ID is required")
        
        logger.debug(f"Transaction validated: {transaction.transaction_id}")

    def _check_duplicate(self, idempotency_key: str) -> Optional[TransactionResponse]:
        """Check if transaction already exists.
        
        Args:
            idempotency_key: Idempotency key to check
            
        Returns:
            Transaction response if duplicate, None otherwise
        """
        dedup_key = self._generate_dedup_key(idempotency_key)
        cached_value = self.redis.get(dedup_key)
        
        if cached_value:
            try:
                data = json.loads(cached_value)
                return TransactionResponse(**data)
            except Exception as e:
                logger.warning(f"Failed to deserialize cached transaction: {e}")
                return None
        
        return None

    def _store_idempotency_key(
        self,
        idempotency_key: str,
        transaction: TransactionResponse
    ) -> None:
        """Store idempotency key in Redis.
        
        Args:
            idempotency_key: Idempotency key
            transaction: Transaction response to cache
        """
        dedup_key = self._generate_dedup_key(idempotency_key)
        try:
            self.redis.setex(
                dedup_key,
                self.dedup_ttl,
                json.dumps(transaction.dict(), default=str)
            )
            logger.debug(f"Stored idempotency key: {dedup_key}")
        except Exception as e:
            logger.error(f"Failed to store idempotency key: {e}")
            # Don't raise - deduplication is best-effort

    async def _publish_to_kafka(
        self,
        topic: str,
        transaction: dict
    ) -> None:
        """Publish transaction to Kafka topic.
        
        Args:
            topic: Kafka topic
            transaction: Transaction data
        """
        # Use transaction ID as partition key for ordering
        partition_key = transaction['transaction_id'].encode('utf-8')
        
        future = self.producer.send(
            topic,
            value=transaction,
            key=partition_key
        )
        
        # Wait for confirmation
        try:
            record_metadata = future.get(timeout=5)
            logger.debug(
                f"Published to {record_metadata.topic} "
                f"partition {record_metadata.partition} "
                f"offset {record_metadata.offset}"
            )
        except KafkaError as e:
            logger.error(f"Failed to publish to Kafka: {e}")
            raise

    def get_transaction_status(
        self,
        transaction_id: str
    ) -> Optional[dict]:
        """Retrieve transaction status.
        
        Args:
            transaction_id: Transaction ID
            
        Returns:
            Transaction status data or None
        """
        # This would typically query the database
        # For now, return placeholder
        logger.info(f"Retrieving status for: {transaction_id}")
        return None

    @staticmethod
    def _generate_dedup_key(idempotency_key: str) -> str:
        """Generate Redis key for idempotency.
        
        Args:
            idempotency_key: Client-provided idempotency key
            
        Returns:
            Redis key
        """
        hash_obj = hashlib.sha256(idempotency_key.encode('utf-8'))
        return f"dedup:{hash_obj.hexdigest()}"

    def shutdown(self) -> None:
        """Graceful shutdown."""
        if self.producer:
            self.producer.flush()
            self.producer.close()
            logger.info("Kafka producer shut down")
