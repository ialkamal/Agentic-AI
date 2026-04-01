"""
FastAPI wrapper for the Paper Supply Agent System
Handles HTTP requests for order processing and quote generation
"""

import os
from typing import Dict, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
import logging

# Import from project_starter module
try:
    from project_starter import (
        Orchestrator,
        ensure_database_ready,
        model,
    )
except ImportError as e:
    print(f"Warning: Could not import from project_starter: {e}")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Paper Supply Agent API",
    description="Multi-agent system for processing orders and generating quotes",
    version="1.0.0"
)

# =========================================================
# REQUEST/RESPONSE MODELS
# =========================================================

class OrderRequest(BaseModel):
    """Request model for processing a customer order"""
    customer_request: str
    request_date: Optional[str] = None
    context: Optional[str] = None


class OrderResponse(BaseModel):
    """Response model for completed order processing"""
    status: str
    request_id: str
    parsed_items: list
    inventory_assessment: Dict
    quote: Optional[Dict] = None
    order_id: Optional[int] = None
    transactions: Optional[list] = None
    error_message: Optional[str] = None
    timestamp: str


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: str
    version: str


orchestrator = None


def _build_customer_request(request: OrderRequest) -> str:
    customer_request = request.customer_request

    if request.context:
        customer_request = f"Context: {request.context}\n\n{customer_request}"

    if request.request_date:
        customer_request += f"\n\n(Date of request: {request.request_date})"

    return customer_request


# =========================================================
# HEALTH CHECK ENDPOINTS
# =========================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for load balancers and monitoring"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0"
    )


@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint"""
    return {"status": "ready"}


# =========================================================
# ORDER PROCESSING ENDPOINTS
# =========================================================

@app.post("/process-order", response_model=OrderResponse)
async def process_order(request: OrderRequest):
    """
    Process a customer order request and generate a quote
    
    Args:
        request: OrderRequest containing customer request text
        
    Returns:
        OrderResponse with processing results
    """
    
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Service is not ready")

    request_id = f"REQ-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    
    try:
        logger.info(f"Processing request {request_id}")
        
        customer_request = _build_customer_request(request)

        parsed = orchestrator.parser.parse_request(customer_request)
        parsed_items = [
            {
                "requested_name": item.requested_name,
                "canonical_name": item.canonical_name,
                "quantity": item.quantity,
            }
            for item in parsed.items
        ]

        if not parsed.items:
            return OrderResponse(
                status="failed",
                request_id=request_id,
                parsed_items=[],
                inventory_assessment={},
                error_message=(
                    "We could not identify any orderable paper items in your request. "
                    "Please resend your request with quantities and product descriptions."
                ),
                timestamp=datetime.utcnow().isoformat(),
            )

        inventory_assessment = orchestrator.inventory_manager.assess_request(parsed)

        if len(inventory_assessment["supported_items"]) == 0:
            unsupported = inventory_assessment["unsupported_items"] + inventory_assessment["blocked_items"]
            reasons = "; ".join(
                [f"{x.get('requested_name', x.get('item_name'))}: {x.get('reason', 'not available')}" for x in unsupported]
            )
            return OrderResponse(
                status="failed",
                request_id=request_id,
                parsed_items=parsed_items,
                inventory_assessment=inventory_assessment,
                error_message=f"We are unable to fulfill this request at this time. Reason(s): {reasons}.",
                timestamp=datetime.utcnow().isoformat(),
            )

        quote = orchestrator.quote_processor.generate_quote(parsed, inventory_assessment)

        if inventory_assessment["can_fulfill"]:
            order_result = orchestrator.order_processor.finalize_order(parsed, inventory_assessment, quote)
            executed_transactions = order_result.get("transactions", [])
            order_id = executed_transactions[0]["id"] if executed_transactions else None
            return OrderResponse(
                status=order_result.get("status", "fulfilled"),
                request_id=request_id,
                parsed_items=parsed_items,
                inventory_assessment=inventory_assessment,
                quote=quote,
                order_id=order_id,
                transactions=executed_transactions,
                timestamp=datetime.utcnow().isoformat(),
            )

        blocked_reasons = "; ".join(
            [f"{x['item_name']}: {x['reason']}" for x in inventory_assessment["blocked_items"]]
        )
        unsupported_reasons = "; ".join(
            [f"{x['requested_name']}: {x['reason']}" for x in inventory_assessment["unsupported_items"]]
        )
        all_reasons = "; ".join([r for r in [blocked_reasons, unsupported_reasons] if r])

        return OrderResponse(
            status="partial",
            request_id=request_id,
            parsed_items=parsed_items,
            inventory_assessment=inventory_assessment,
            quote=quote,
            error_message=(
                "We can quote some matched items, but we cannot fully fulfill the complete request "
                f"by the requested timeline. Reason(s): {all_reasons}."
            ),
            timestamp=datetime.utcnow().isoformat(),
        )
        
    except Exception as e:
        logger.error(f"Error processing request {request_id}: {str(e)}")
        return OrderResponse(
            status="failed",
            request_id=request_id,
            parsed_items=[],
            inventory_assessment={},
            error_message=str(e),
            timestamp=datetime.utcnow().isoformat()
        )


@app.post("/quote")
async def get_quote(request: OrderRequest):
    """
    Generate a quote for a customer request without creating an order
    
    Args:
        request: OrderRequest containing customer request text
        
    Returns:
        Quote information
    """
    
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Service is not ready")

    try:
        logger.info("Generating quote")

        customer_request = _build_customer_request(request)
        parsed = orchestrator.parser.parse_request(customer_request)

        if not parsed.items:
            return {
                "status": "failed",
                "parsed_items": [],
                "quote": None,
                "error_message": (
                    "We could not identify any orderable paper items in your request. "
                    "Please resend your request with quantities and product descriptions."
                ),
                "timestamp": datetime.utcnow().isoformat(),
            }

        inventory_assessment = orchestrator.inventory_manager.assess_request(parsed)
        if len(inventory_assessment["supported_items"]) == 0:
            return {
                "status": "failed",
                "parsed_items": [
                    {
                        "requested_name": item.requested_name,
                        "canonical_name": item.canonical_name,
                        "quantity": item.quantity,
                    }
                    for item in parsed.items
                ],
                "quote": None,
                "inventory_assessment": inventory_assessment,
                "error_message": "No supported catalog items available to quote.",
                "timestamp": datetime.utcnow().isoformat(),
            }

        quote = orchestrator.quote_processor.generate_quote(parsed, inventory_assessment)

        return {
            "status": "success",
            "parsed_items": [
                {
                    "requested_name": item.requested_name,
                    "canonical_name": item.canonical_name,
                    "quantity": item.quantity,
                }
                for item in parsed.items
            ],
            "inventory_assessment": inventory_assessment,
            "quote": quote,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Error generating quote: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to generate quote: {str(e)}"
        )


# =========================================================
# STARTUP/SHUTDOWN EVENTS
# =========================================================

@app.on_event("startup")
async def startup_event():
    """Initialize on application startup"""
    logger.info("Starting Paper Supply Agent API")
    global orchestrator
    ensure_database_ready()
    orchestrator = Orchestrator(model)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down Paper Supply Agent API")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
