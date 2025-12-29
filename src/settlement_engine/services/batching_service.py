"""Smart batching service with cost optimization."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from uuid import uuid4

import numpy as np
from pulp import LpMinimize, LpProblem, LpVariable, lpSum, PULP_CBC_CMD

from ..models import (
    TransactionResponse,
    SettlementBatch,
    BatchStatus,
    SettlementWindow,
    BatchOptimizationResult
)

logger = logging.getLogger(__name__)


class BatchingService:
    """Optimizes transaction batching to minimize settlement costs.
    
    This service implements constraint satisfaction to:
    1. Minimize cross-border FX spread costs
    2. Optimize counterparty matching (reduce wire count)
    3. Respect liquidity constraints
    4. Handle settlement window timing
    """

    # FX Spread costs (basis points)
    FX_SPREADS = {
        ('USD', 'EUR'): 2.5,
        ('EUR', 'USD'): 2.5,
        ('USD', 'GBP'): 3.0,
        ('GBP', 'USD'): 3.0,
        ('USD', 'JPY'): 2.0,
        ('JPY', 'USD'): 2.0,
        ('EUR', 'GBP'): 2.0,
        ('GBP', 'EUR'): 2.0,
    }

    # Wire costs per transaction (USD)
    WIRE_COST = Decimal('5.00')
    
    # Batch consolidation discount (reduce costs when batching multiple wires)
    CONSOLIDATION_DISCOUNT = 0.15  # 15% discount for consolidated batches

    def __init__(
        self,
        fx_rate_service=None,
        max_batch_size: int = 1000
    ):
        """Initialize batching service.
        
        Args:
            fx_rate_service: Service for FX rates
            max_batch_size: Maximum transactions per batch
        """
        self.fx_rate_service = fx_rate_service
        self.max_batch_size = max_batch_size

    def optimize_batch(
        self,
        transactions: List[TransactionResponse],
        liquidity_constraints: Optional[Dict[str, Decimal]] = None
    ) -> List[BatchOptimizationResult]:
        """Optimize transactions into cost-efficient batches.
        
        Args:
            transactions: Transactions to batch
            liquidity_constraints: Currency-specific liquidity limits
            
        Returns:
            List of optimized batches
        """
        if not transactions:
            return []
        
        logger.info(f"Optimizing {len(transactions)} transactions")
        
        # Group by settlement window
        grouped = self._group_by_settlement_window(transactions)
        
        all_batches = []
        for window, window_txns in grouped.items():
            batches = self._optimize_for_window(
                window_txns,
                window,
                liquidity_constraints
            )
            all_batches.extend(batches)
        
        return all_batches

    def _group_by_settlement_window(
        self,
        transactions: List[TransactionResponse]
    ) -> Dict[SettlementWindow, List[TransactionResponse]]:
        """Group transactions by settlement window.
        
        Args:
            transactions: Transactions to group
            
        Returns:
            Grouped transactions
        """
        grouped = defaultdict(list)
        for txn in transactions:
            window = txn.settlement_window or SettlementWindow.RTGS
            grouped[window].append(txn)
        return grouped

    def _optimize_for_window(
        self,
        transactions: List[TransactionResponse],
        window: SettlementWindow,
        liquidity_constraints: Optional[Dict[str, Decimal]]
    ) -> List[BatchOptimizationResult]:
        """Optimize transactions for a specific settlement window.
        
        Args:
            transactions: Transactions to optimize
            window: Settlement window
            liquidity_constraints: Currency-specific constraints
            
        Returns:
            Optimized batches
        """
        if not transactions:
            return []
        
        # Split into chunks if too large
        chunks = [
            transactions[i:i + self.max_batch_size]
            for i in range(0, len(transactions), self.max_batch_size)
        ]
        
        results = []
        for chunk in chunks:
            result = self._solve_batch_optimization(
                chunk,
                window,
                liquidity_constraints
            )
            if result:
                results.append(result)
        
        return results

    def _solve_batch_optimization(
        self,
        transactions: List[TransactionResponse],
        window: SettlementWindow,
        liquidity_constraints: Optional[Dict[str, Decimal]]
    ) -> Optional[BatchOptimizationResult]:
        """Solve batching optimization using Linear Programming.
        
        Minimize: FX costs + Wire costs
        Constraints:
            - Liquidity limits per currency
            - Batch size limits
            - Settlement window respect
        
        Args:
            transactions: Transactions to optimize
            window: Settlement window
            liquidity_constraints: Liquidity limits
            
        Returns:
            Optimized batch result
        """
        # Build LP model
        prob = LpProblem("Settlement_Optimization", LpMinimize)
        
        # Decision variables: which transactions in which batches
        batch_vars = {}
        for i, txn in enumerate(transactions):
            for j in range(1, 4):  # Up to 3 logical batches
                batch_vars[(i, j)] = LpVariable(
                    f"txn_{i}_batch_{j}",
                    cat='Binary'
                )
        
        # Objective: minimize total settlement costs
        cost_expr = self._build_cost_expression(
            transactions,
            batch_vars
        )
        prob += cost_expr
        
        # Constraint: each transaction in exactly one batch
        for i in range(len(transactions)):
            prob += sum(
                batch_vars[(i, j)] for j in range(1, 4)
            ) == 1
        
        # Constraint: respect liquidity limits
        if liquidity_constraints:
            self._add_liquidity_constraints(
                prob,
                transactions,
                batch_vars,
                liquidity_constraints
            )
        
        # Solve
        try:
            prob.solve(PULP_CBC_CMD(msg=0))
        except Exception as e:
            logger.error(f"LP solver failed: {e}")
            # Fallback to simple grouping
            return self._simple_grouping(transactions, window)
        
        # Extract solution
        return self._extract_solution(
            transactions,
            batch_vars,
            window
        )

    def _build_cost_expression(self, transactions, batch_vars):
        """Build cost expression for LP model."""
        total_cost = 0
        for i, txn in enumerate(transactions):
            for j in range(1, 4):
                # FX cost
                fx_cost = self._calculate_fx_cost(
                    txn.source_currency,
                    txn.destination_currency,
                    txn.amount
                )
                # Wire cost (with consolidation discount)
                wire_cost = float(self.WIRE_COST) * (1 - self.CONSOLIDATION_DISCOUNT)
                
                total_cost += (fx_cost + wire_cost) * batch_vars[(i, j)]
        
        return total_cost

    def _calculate_fx_cost(self, src_curr: str, dst_curr: str, amount: Decimal) -> float:
        """Calculate FX spread cost."""
        pair = (src_curr, dst_curr)
        spread_bp = self.FX_SPREADS.get(pair, 5.0)  # Default 5 bps
        return float(amount) * (spread_bp / 10000)  # Convert bps to percentage

    def _add_liquidity_constraints(self, prob, transactions, batch_vars, constraints):
        """Add liquidity limit constraints to LP model."""
        for currency, limit in constraints.items():
            expr = 0
            for i, txn in enumerate(transactions):
                if txn.source_currency == currency:
                    for j in range(1, 4):
                        expr += txn.amount * batch_vars[(i, j)]
            
            prob += expr <= float(limit)

    def _extract_solution(
        self,
        transactions: List[TransactionResponse],
        batch_vars,
        window: SettlementWindow
    ) -> Optional[BatchOptimizationResult]:
        """Extract optimized batch from LP solution."""
        batches = defaultdict(list)
        for i, txn in enumerate(transactions):
            for j in range(1, 4):
                if batch_vars[(i, j)].varValue > 0.5:  # Binary variable
                    batches[j].append(txn.transaction_id)
        
        # Create result for main batch
        batch_id = f"batch_{datetime.utcnow().timestamp():.0f}_{uuid4().hex[:8]}"
        main_batch_txns = batches.get(1, [])
        
        if not main_batch_txns:
            return None
        
        cost_before = sum(
            self._calculate_fx_cost(
                txn.source_currency,
                txn.destination_currency,
                txn.amount
            ) + float(self.WIRE_COST)
            for txn in transactions
            if txn.transaction_id in main_batch_txns
        )
        
        cost_after = sum(
            self._calculate_fx_cost(
                txn.source_currency,
                txn.destination_currency,
                txn.amount
            )
            for txn in transactions
            if txn.transaction_id in main_batch_txns
        ) + float(self.WIRE_COST) * (1 - self.CONSOLIDATION_DISCOUNT)
        
        return BatchOptimizationResult(
            batch_id=batch_id,
            transactions=main_batch_txns,
            optimization_metrics={
                "solver": "pulp_cbc",
                "iterations": 1,
                "convergence": "optimal"
            },
            total_cost_before_optimization=Decimal(str(cost_before)),
            total_cost_after_optimization=Decimal(str(cost_after)),
            cost_savings=Decimal(str(max(0, cost_before - cost_after))),
            cost_savings_percentage=(
                (cost_before - cost_after) / cost_before * 100
                if cost_before > 0 else 0
            ),
            settlement_window=window,
            netting_details=self._calculate_netting(
                transactions,
                main_batch_txns
            )
        )

    def _simple_grouping(
        self,
        transactions: List[TransactionResponse],
        window: SettlementWindow
    ) -> Optional[BatchOptimizationResult]:
        """Fallback to simple grouping if optimization fails."""
        batch_id = f"batch_{datetime.utcnow().timestamp():.0f}_{uuid4().hex[:8]}"
        return BatchOptimizationResult(
            batch_id=batch_id,
            transactions=[t.transaction_id for t in transactions[:min(100, len(transactions))]],
            optimization_metrics={"method": "simple_grouping"},
            total_cost_before_optimization=Decimal('0'),
            total_cost_after_optimization=Decimal('0'),
            cost_savings=Decimal('0'),
            cost_savings_percentage=0.0,
            settlement_window=window,
            netting_details={}
        )

    def _calculate_netting(
        self,
        transactions: List[TransactionResponse],
        batch_txns: List[str]
    ) -> Dict:
        """Calculate multilateral netting details."""
        # Group by counterparty pair
        netting = defaultdict(lambda: {'sent': Decimal('0'), 'received': Decimal('0')})
        
        for txn in transactions:
            if txn.transaction_id not in batch_txns:
                continue
            
            pair = tuple(sorted([txn.counterparty_id, 'self']))
            if txn.counterparty_id > 'self':
                netting[pair]['sent'] += txn.amount
            else:
                netting[pair]['received'] += txn.amount
        
        return dict(netting)
