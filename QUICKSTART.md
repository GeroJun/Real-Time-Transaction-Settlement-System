# Quick Start Guide

## Prerequisites

- Docker & Docker Compose (v20+)
- Python 3.11+ (for local development)
- Git
- 8GB RAM, 20GB disk space recommended

## 5-Minute Local Setup

### 1. Clone Repository

```bash
git clone https://github.com/GeroJun/Real-Time-Transaction-Settlement-System.git
cd Real-Time-Transaction-Settlement-System
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env if needed (defaults work for local development)
```

### 3. Start Infrastructure

```bash
docker-compose up -d
```

This starts:
- PostgreSQL database
- Redis cache
- Apache Kafka with Zookeeper
- etcd for consensus
- Prometheus metrics
- Grafana dashboards
- Settlement Engine API

**Wait for healthy status:**
```bash
# Check all services
docker-compose ps

# Expected output (all should have status 'Up (healthy)'):
# settlement-engine   Up (healthy)
# postgres            Up (healthy)
# redis               Up (healthy)
# kafka               Up (healthy)
# etcd                Up (healthy)
```

### 4. Verify Installation

```bash
# Check API health
curl http://localhost:8000/api/v1/health

# Expected response:
{
  "status": "healthy",
  "kafka_status": "healthy",
  "database_status": "healthy",
  "redis_status": "healthy",
  "consensus_status": "healthy"
}
```

### 5. Access Dashboards

- **API Documentation**: http://localhost:8000/docs (Swagger UI)
- **Grafana Dashboards**: http://localhost:3001 (admin/admin)
- **Prometheus**: http://localhost:9090

---

## Usage Examples

### Submit a Transaction

```bash
curl -X POST http://localhost:8000/api/v1/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "txn_$(date +%s)",
    "amount": "100000.00",
    "source_currency": "USD",
    "destination_currency": "EUR",
    "source_account": "acc_001",
    "destination_account": "acc_002",
    "counterparty_id": "bank_a",
    "idempotency_key": "req_$(date +%s)_$RANDOM",
    "settlement_window": "rtgs"
  }'
```

**Response:**
```json
{
  "transaction_id": "txn_1704067800",
  "amount": "100000.00",
  "source_currency": "USD",
  "destination_currency": "EUR",
  "status": "submitted",
  "created_at": "2025-12-29T07:10:00Z"
}
```

### Check System Metrics

```bash
curl http://localhost:8000/api/v1/metrics
```

### Query Liquidity Forecast

```bash
curl 'http://localhost:8000/api/v1/liquidity/forecast?currency=EUR&days_ahead=7'
```

### Monitor Counterparty Risk

```bash
curl http://localhost:8000/api/v1/risk/counterparties
```

---

## Testing

### Unit Tests

```bash
# Install test dependencies
pip install -r requirements.txt

# Run tests
pytest src/tests/test_intake_service.py -v

# With coverage
pytest src/tests/ --cov=src --cov-report=html
```

### Load Testing (Target: 10,000 TPS)

```bash
# Install Locust
pip install locust

# Run load test (10,000 concurrent users, 1,000 ramp-up rate, 5 min duration)
locust -f src/tests/test_load.py \
  --headless \
  -u 10000 \
  -r 1000 \
  -t 5m \
  -H http://localhost:8000
```

**Expected Results:**
```
|-----|--------|--------|
Type    | Name           | # requests | # failures | Avg | Min | Max | Median | req/s
POST    | /api/v1/transactions | 15000 | 0 | 25.3 | 8.2 | 95.1 | 23 | 50.0
GET     | /api/v1/health | 2000 | 0 | 12.1 | 4.3 | 45.2 | 11 | 6.7
GET     | /api/v1/metrics | 500 | 0 | 18.9 | 6.1 | 67.3 | 17 | 1.7
|-----|--------|--------|
Total   | | 17500 | 0 | 23.0 | 4.3 | 95.1 | 22 | 58.3 (TPS)
```

---

## Development Workflow

### Add New Feature

1. Create feature branch:
   ```bash
   git checkout -b feature/my-feature
   ```

2. Make changes in `src/settlement_engine/`

3. Write tests:
   ```bash
   # Add test in src/tests/test_*.py
   pytest src/tests/test_my_feature.py -v
   ```

4. Run linting:
   ```bash
   black src/
   flake8 src/
   mypy src/
   ```

5. Commit and push:
   ```bash
   git add .
   git commit -m "feat: add my feature"
   git push origin feature/my-feature
   ```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Add new table"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

---

## Monitoring & Debugging

### View Logs

```bash
# Settlement engine logs
docker-compose logs -f settlement-engine

# Kafka logs
docker-compose logs -f kafka

# All services
docker-compose logs -f
```

### Database Access

```bash
# Connect to PostgreSQL
docker exec -it settlement-system_postgres_1 psql -U settlement -d settlement_engine

# Query transactions
SELECT * FROM settlement_ledger LIMIT 10;
```

### Redis Cache Inspection

```bash
# Connect to Redis
docker exec -it settlement-system_redis_1 redis-cli

# View dedup keys
KEYS dedup:*

# Get specific key
GET dedup:abc123
```

### Kafka Topic Inspection

```bash
# List topics
docker exec -it settlement-system_kafka_1 kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list

# View topic messages
docker exec -it settlement-system_kafka_1 kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic transactions.intake \
  --from-beginning
```

---

## Troubleshooting

### Services won't start

```bash
# Check Docker daemon
docker ps

# Rebuild containers
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Check service health
docker-compose ps
```

### PostgreSQL connection timeout

```bash
# Check if postgres is ready
docker-compose exec postgres pg_isready -U settlement

# Force restart
docker-compose restart postgres
```

### Kafka not available

```bash
# Check Zookeeper
docker-compose logs zookeeper | tail -20

# Restart Kafka cluster
docker-compose restart zookeeper kafka
```

### High memory usage

```bash
# Check memory per container
docker stats

# Reduce Kafka memory
# Edit docker-compose.yml, set KAFKA_HEAP_OPTS=-Xmx512M
```

---

## Cleanup

### Stop Services

```bash
# Stop but keep data
docker-compose stop

# Stop and remove containers
docker-compose down

# Remove volumes (WARNING: deletes data)
docker-compose down -v
```

---

## Next Steps

1. **Read Architecture**: See `docs/ARCHITECTURE.md` for system design details
2. **Deploy to Kubernetes**: See `docs/DEPLOYMENT.md` for K8s setup
3. **Advanced Configuration**: See `.env.example` for all available options
4. **API Reference**: Visit http://localhost:8000/docs for interactive API docs
5. **Contribute**: See `CONTRIBUTING.md` for development guidelines

---

## Performance Optimization Tips

### Increase Throughput

```bash
# Edit docker-compose.yml environment:
WORKERS=8                          # Increase workers
BATCH_TIMEOUT_SECONDS=60           # Longer batching window
KAFKA_LINGER_MS=20                 # More batching
```

### Reduce Latency

```bash
# Edit docker-compose.yml environment:
BATCH_TIMEOUT_SECONDS=10           # Shorter window
KAFKA_LINGER_MS=1                  # Less latency
REDIS_SOCKET_KEEPALIVE=True        # Better connection reuse
```

### Monitor Performance

```bash
# Watch metrics in real-time
watch -n 1 'curl -s http://localhost:8000/api/v1/metrics | jq .throughput_tps'
```

---

For more help, see:
- `README.md` - Project overview
- `docs/` - Detailed documentation
- Issues: https://github.com/GeroJun/Real-Time-Transaction-Settlement-System/issues
