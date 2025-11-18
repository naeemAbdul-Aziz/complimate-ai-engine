# api/error_handlers.py
"""
Centralized Exception Handlers for the FastAPI Application.
"""
import logging
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

# Get a logger for this module
logger = logging.getLogger(__name__)

async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Handles and logs HTTPErrors, returning a standardized JSON response.
    """
    logger.warning(
        f"HTTP Exception caught: {exc.status_code} {exc.detail} for request {request.method} {request.url.path}"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": exc.detail, "data": None},
    )

async def general_exception_handler(request: Request, exc: Exception):
    """
    Handles and logs any unhandled exceptions, returning a generic 500 error.
    This prevents internal error details from leaking to the client.
    """
    logger.error(
        f"Unhandled exception caught: {exc.__class__.__name__} for request {request.method} {request.url.path}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "An unexpected internal server error occurred.",
            "data": None,
        },
    )
