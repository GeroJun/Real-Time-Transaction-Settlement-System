"""Unit tests for intake service."""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch
import redis
from kafka import KafkaProducer

from ..settlement_engine.models import TransactionRequest, TransactionStatus
from ..settlement_engine.services.intake_service import IntakeService


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    return MagicMock(spec=redis.Redis)


@pytest.fixture
def intake_service(mock_redis):
    """Create intake service with mocks."""
    with patch.object(KafkaProducer, '__init__', lambda x, **kwargs: None):
        service = IntakeService(
            redis_client=mock_redis,
            kafka_bootstrap_servers=['localhost:9092']
        )
        service.producer = MagicMock(spec=KafkaProducer)
    return service


class TestTransactionValidation:
    """Test transaction validation."""

    def test_valid_transaction(self):
        """Test valid transaction passes validation."""
        request = TransactionRequest(
            transaction_id="txn_001",
            amount=Decimal('1000.00'),
            source_currency="USD",
            destination_currency="EUR",
            source_account="acc_001",
            destination_account="acc_002",
            counterparty_id="bank_a",
            idempotency_key="req_001"
        )
        
        intake_service = IntakeService(
            redis_client=MagicMock(),
            kafka_bootstrap_servers=['localhost:9092']
        )
        
        # Should not raise
        intake_service._validate_transaction(request)

    def test_invalid_amount(self):
        """Test negative amount fails validation."""
        request = TransactionRequest(
            transaction_id="txn_001",
            amount=Decimal('-100.00'),  # Invalid
            source_currency="USD",
            destination_currency="EUR",
            source_account="acc_001",
            destination_account="acc_002",
            counterparty_id="bank_a",
            idempotency_key="req_001"
        )
        
        service = IntakeService(
            redis_client=MagicMock(),
            kafka_bootstrap_servers=['localhost:9092']
        )
        
        with pytest.raises(ValueError):
            service._validate_transaction(request)

    def test_same_source_destination(self):
        """Test same source and destination account fails."""
        request = TransactionRequest(
            transaction_id="txn_001",
            amount=Decimal('1000.00'),
            source_currency="USD",
            destination_currency="USD",
            source_account="acc_001",
            destination_account="acc_001",  # Same as source
            counterparty_id="bank_a",
            idempotency_key="req_001"
        )
        
        service = IntakeService(
            redis_client=MagicMock(),
            kafka_bootstrap_servers=['localhost:9092']
        )
        
        with pytest.raises(ValueError):
            service._validate_transaction(request)

    def test_unsupported_currency(self):
        """Test unsupported currency fails validation."""
        with pytest.raises(ValueError, match="Unsupported currency"):
            TransactionRequest(
                transaction_id="txn_001",
                amount=Decimal('1000.00'),
                source_currency="XYZ",  # Invalid
                destination_currency="USD",
                source_account="acc_001",
                destination_account="acc_002",
                counterparty_id="bank_a",
                idempotency_key="req_001"
            )


class TestDeduplication:
    """Test idempotency and deduplication."""

    def test_dedup_key_generation(self):
        """Test dedup key generation is deterministic."""
        key1 = IntakeService._generate_dedup_key("test_key")
        key2 = IntakeService._generate_dedup_key("test_key")
        
        assert key1 == key2
        assert key1.startswith("dedup:")

    def test_duplicate_detection(self, intake_service, mock_redis):
        """Test duplicate detection via Redis."""
        import json
        
        # Setup mock to return a cached transaction
        cached_txn = {
            "transaction_id": "txn_001",
            "amount": "1000.00",
            "source_currency": "USD",
            "destination_currency": "EUR",
            "source_account": "acc_001",
            "destination_account": "acc_002",
            "counterparty_id": "bank_a",
            "idempotency_key": "req_001",
            "status": "submitted"
        }
        mock_redis.get.return_value = json.dumps(cached_txn)
        
        result = intake_service._check_duplicate("req_001")
        
        assert result is not None
        assert result.transaction_id == "txn_001"


class TestKafkaPublishing:
    """Test Kafka message publishing."""

    @pytest.mark.asyncio
    async def test_publish_to_kafka(self, intake_service):
        """Test publishing transaction to Kafka."""
        from unittest.mock import AsyncMock, MagicMock
        
        # Mock future
        future = MagicMock()
        future.get.return_value = MagicMock(topic="transactions.intake")
        intake_service.producer.send.return_value = future
        
        transaction = {
            "transaction_id": "txn_001",
            "amount": "1000.00"
        }
        
        # Should not raise
        await intake_service._publish_to_kafka(
            "transactions.intake",
            transaction
        )
        
        intake_service.producer.send.assert_called_once()
