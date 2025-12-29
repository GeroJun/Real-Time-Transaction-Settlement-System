"""Load testing with Locust.

Run with:
    locust -f src/tests/test_load.py --headless -u 10000 -r 1000 -t 5m
"""

from decimal import Decimal
import random
import string
from locust import HttpUser, task, between, events
import json


class SettlementLoadTest(HttpUser):
    """Load test for settlement system."""
    
    wait_time = between(0.1, 0.5)  # Random wait between 100-500ms
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.transaction_counter = 0
    
    @task(70)
    def submit_transaction(self):
        """Submit transaction - 70% of traffic."""
        self.transaction_counter += 1
        
        transaction_id = f"txn_{self.client.environment.host}_{self.transaction_counter}"
        idempotency_key = f"req_{self.transaction_counter}_{random.randint(0, 1000000)}"
        
        payload = {
            "transaction_id": transaction_id,
            "amount": f"{random.randint(100, 999999)}.00",
            "source_currency": random.choice(["USD", "EUR", "GBP", "JPY"]),
            "destination_currency": random.choice(["USD", "EUR", "GBP", "JPY"]),
            "source_account": f"acc_{random.randint(1, 1000)}",
            "destination_account": f"acc_{random.randint(1, 1000)}",
            "counterparty_id": f"bank_{random.choice(['a', 'b', 'c', 'd'])}",
            "idempotency_key": idempotency_key,
            "settlement_window": random.choice(["rtgs", "t0", "t1", "t2"])
        }
        
        with self.client.post(
            "/api/v1/transactions",
            json=payload,
            catch_response=True
        ) as response:
            if response.status_code in [201, 409]:  # Created or Conflict (duplicate)
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")
    
    @task(20)
    def check_health(self):
        """Check system health - 20% of traffic."""
        with self.client.get("/api/v1/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")
    
    @task(5)
    def get_metrics(self):
        """Get system metrics - 5% of traffic."""
        with self.client.get("/api/v1/metrics", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Metrics endpoint failed: {response.status_code}")
    
    @task(3)
    def query_liquidity(self):
        """Query liquidity forecast - 3% of traffic."""
        currency = random.choice(["USD", "EUR", "GBP", "JPY"])
        with self.client.get(
            f"/api/v1/liquidity/forecast?currency={currency}&days_ahead=7",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Liquidity forecast failed: {response.status_code}")
    
    @task(2)
    def query_counterparty_risk(self):
        """Query counterparty risk - 2% of traffic."""
        with self.client.get("/api/v1/risk/counterparties", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Counterparty risk query failed: {response.status_code}")


def print_stats(environment, **kwargs):
    """Print test statistics."""
    print("\n" + "="*70)
    print("LOAD TEST SUMMARY")
    print("="*70)
    
    # Access request stats
    for name, stats in sorted(environment.stats.entries.items()):
        total = stats.num_requests
        failures = stats.num_failures
        
        if total:
            failure_rate = (failures / total) * 100
            print(
                f"{name:30} | "
                f"Requests: {total:6} | "
                f"Failures: {failures:4} ({failure_rate:5.2f}%) | "
                f"Avg: {stats.avg_response_time:7.2f}ms | "
                f"P95: {stats.get_response_time_percentile(0.95):7.2f}ms"
            )


# Hook for test completion
events.test_stop.add_listener(print_stats)
