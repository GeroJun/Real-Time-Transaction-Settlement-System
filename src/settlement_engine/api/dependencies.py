from fastapi import Request
from src.settlement_engine.services.intake_service import IntakeService

def get_intake_service(request: Request) -> IntakeService:
    """
    Fetch the IntakeService that was initialized in main.py.
    
    This ensures we reuse the SAME Redis and Kafka connections 
    instead of opening new ones for every single request.
    """
    # This 'intake_service' is the one we created in main.py's lifespan function
    return request.app.state.intake_service