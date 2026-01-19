from fastapi import APIRouter, Depends, HTTPException, status, Response
from src.settlement_engine.models import TransactionRequest, TransactionResponse, TransactionStatus
from src.settlement_engine.services.intake_service import IntakeService
# This now works because we created the file above
from src.settlement_engine.api.dependencies import get_intake_service

router = APIRouter()

@router.post(
    "/",  # ✅ FIX: Use "/" because the prefix is already defined in main.py
    response_model=TransactionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a new transaction",
    description="Validates, dedupes, and queues a transaction for settlement."
)
async def submit_transaction(
    request: TransactionRequest,
    response: Response,  # ✅ FIX: Inject Response object to modify status code
    service: IntakeService = Depends(get_intake_service)
):
    """
    Ingest a new transaction request.
    
    - **202 Accepted**: Transaction is valid and queued.
    - **200 OK**: Transaction is a duplicate (idempotent response).
    - **400 Bad Request**: Validation failed.
    """
    try:
        # Pass the request to the service layer
        result = await service.process_transaction(request)
        
        # ✅ FIX: Actually apply the status code change
        if result.status == TransactionStatus.DEDUPED:
            response.status_code = status.HTTP_200_OK
        else:
            response.status_code = status.HTTP_202_ACCEPTED
        
        # Return the response
        # Note: We rely on the service returning a compatible object
        # or we explicitly map it here to be safe.
        return TransactionResponse(
            transaction_id=result.transaction_id,
            status=result.status,
            message=result.message if hasattr(result, "message") else "Transaction processed",
            batch_id=result.metadata.get("batch_id") if result.metadata else None,
            metadata=result.metadata if result.metadata else {}
        )
            
    except ValueError as e:
        # Catch business logic errors (like 'Unsupported Currency')
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Catch unexpected server crashes
        print(f"CRITICAL ERROR: {e}")
        raise HTTPException(status_code=500, detail="Internal settlement engine error")