from fastapi import APIRouter, Depends, HTTPException, status, Response
from src.settlement_engine.models import TransactionRequest, TransactionResponse, TransactionStatus
from src.settlement_engine.services.intake_service import IntakeService
from src.settlement_engine.api.dependencies import get_intake_service

router = APIRouter()

@router.post(
    "/", 
    response_model=TransactionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a new transaction",
    description="Validates, dedupes, and queues a transaction for settlement."
)
async def submit_transaction(
    request: TransactionRequest,
    response: Response, 
    service: IntakeService = Depends(get_intake_service)
):
    """
    Ingest a new transaction request.
    
    - **202 Accepted**: Transaction is valid and queued.
    - **200 OK**: Transaction is a duplicate (idempotent response).
    - **400 Bad Request**: Validation failed.
    """
    try:
        result = await service.process_transaction(request)

        if result.status == TransactionStatus.DEDUPED:
            response.status_code = status.HTTP_200_OK
        else:
            response.status_code = status.HTTP_202_ACCEPTED
        
        return TransactionResponse(
            transaction_id=result.transaction_id,
            status=result.status,
            message=result.message if hasattr(result, "message") else "Transaction processed",
            batch_id=result.metadata.get("batch_id") if result.metadata else None,
            metadata=result.metadata if result.metadata else {}
        )
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        raise HTTPException(status_code=500, detail="Internal settlement engine error")