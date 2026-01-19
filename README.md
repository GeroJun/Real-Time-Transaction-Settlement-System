# Real-Time Settlement Engine

A high-performance financial gateway built with **Python (FastAPI)** and **Apache Kafka**. This microservice is designed to handle high-throughput transaction intake, enforcing strict settlement windows (T+0, T+1) and ensuring data integrity before transactions ever reach the ledger.

## What I Built

- **High-Throughput Ingestion:** An async API capable of handling burst traffic using non-blocking I/O.
- **Event Streaming Architecture:** Replaced traditional message queues with **Apache Kafka** for real-time log processing.
- **Sub-Millisecond Idempotency:** Implemented a "check-then-set" pattern using **Redis** to prevent double-spending attacks.
- **Strict Schema Validation:** Leveraged **Pydantic** to enforce financial constraints (ISO currency codes, positive amounts) at the edge.
- **Self-Documenting API:** Integrated **OpenAPI 3.1 (Swagger UI)** for seamless frontend/partner integration.

## What I Learned

- How to implement **Event Sourcing** patterns using Kafka topics.
- The difference between **Message Queues** (SQS) and **Event Streams** (Kafka).
- How to enforce complex business logic (Settlement Windows) using Python `Enums` and Pydantic validators.
- Managing application state and "Happy Path" vs. "Edge Case" flows in a distributed system.

## Features

- **Kafka Streaming:** Decouples ingestion from processing, allowing the system to absorb traffic spikes without downtime.
- **Smart Idempotency:** Returns `200 OK` (with original response) for duplicates and `202 Accepted` for new requests, preventing duplicate processing.
- **Settlement Logic:** Automatically routes transactions to `RTGS` (Real-Time), `T0` (Same Day), or `T1` (Next Day) windows based on rules.
- **Defensive Coding:** Rejects invalid financial data (e.g., negative amounts, invalid currency pairs) instantly with `422 Unprocessable Entity`.
- **Containerized Stack:** Fully orchestrated environment (API, Redis, Zookeeper, Kafka) using Docker Compose.

## Components

| Component | Purpose | Technology |
|-----------|---------|------------|
| **Ingestion API** | Async transaction acceptance & validation | Python (FastAPI) |
| **Event Stream** | Durable, replayable log of all transactions | Apache Kafka |
| **State Store** | Idempotency keys & deduplication logic | Redis |
| **Validation Layer** | Enforces data shape and business rules | Pydantic |
| **Orchestrator** | Manages multi-container environment | Docker Compose |

---

## Key Endpoints

### Transaction Intake (The "Happy Path")
```bash
# 1. Submit a new transaction
curl -X POST http://localhost:8000/api/v1/transactions/ \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "txn_001",
    "amount": 250.00,
    "source_currency": "USD",
    "destination_currency": "GBP",
    "source_account": "acct_usa_88",
    "destination_account": "acct_uk_99",
    "counterparty_id": "cparty_london",
    "idempotency_key": "idemp_key_101",
    "settlement_window": "t1"
  }'

# Response: 202 ACCEPTED (Queued)
{
  "transaction_id": "txn_001",
  "status": "submitted",
  "message": "Transaction queued for processing",
  "metadata": { "window": "t1" }
}
```
### Idempotency Check (The "Double-Spend" Protection)
```bash
# 2. Resubmit the EXACT same payload
curl -X POST http://localhost:8000/api/v1/transactions/ ...

# Response: 200 OK (Deduped)
{
  "transaction_id": "txn_001",
  "status": "deduped",
  "message": "Transaction already processed",
  "metadata": { "original_batch": "batch_x99" }
}
```
### System Health
```bash
# Liveness Probe
curl http://localhost:8000/health

# Response
{
  "status": "healthy",
  "service": "settlement-engine",
  "version": "1.0.0"
}
```
---

## 📸 Project Showcase
### Interactive Documentation (Swagger UI)
Fully documented interface allowing developers to test endpoints directly in the browser.
<img width="1440" height="900" alt="OpenAPI:Swagger" src="https://github.com/user-attachments/assets/57b353fd-1735-43a6-b9f2-569ba35fc174" />

### Successful Ingestion (Async)
Valid transactions are acknowledged immediately and queued into Kafka for asynchronous settlement.
<img width="1056" height="715" alt="202 Accepted" src="https://github.com/user-attachments/assets/accc50a6-3db9-4462-826a-e0c5b1e39006" />

### Idempotency in Action
The system detects duplicate idempotency_keys and returns the existing status without re-processing the payment.
<img width="1056" height="715" alt="200 OK : Deduped" src="https://github.com/user-attachments/assets/27ae9f54-82af-4d18-8341-5bcf56997910" />

### Strict Validation (Guardrails)
Attempts to submit negative amounts or invalid currency codes are blocked at the gateway level.
<img width="1056" height="715" alt="422 Unprocessable Entity" src="https://github.com/user-attachments/assets/2f31fcc4-b1e0-4b42-8dca-da557e9074a0" />

---

## Usage

### Quick Start (Docker)

1. **Clone & Build:**
   ```bash
   git clone [https://github.com/GeroJun/Real-Time-Transaction-Settlement-System.git](https://github.com/GeroJun/Real-Time-Transaction-Settlement-System.git)
   cd Real-Time-Transaction-Settlement-System
   docker-compose up --build
2. **Access the API:**

3. **Docs: http://localhost:8000/docs**

4. **Health: http://localhost:8000/health**

5. **Run a Test Transaction: Import the included postman_collection.json or use the curl commands above.**

--- 

## Project Structure

```text
.
├── src/
│   ├── settlement_engine/
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   └── transactions.py   # Endpoint logic
│   │   │   └── dependencies.py       # Dependency Injection
│   │   ├── models.py                 # Pydantic Schemas (Validation)
│   │   ├── services/
│   │   │   └── intake_service.py     # Kafka & Redis Logic
│   │   └── main.py                   # App entrypoint & Lifecycle
├── docker-compose.yml                # Kafka, Zookeeper, Redis, API
├── Dockerfile                        # Python environment
└── README.md                         # This file
