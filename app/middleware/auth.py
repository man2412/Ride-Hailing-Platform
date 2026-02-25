from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from app.config import get_settings

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(data: dict) -> str:
    """Sign a JWT with the configured secret (HS256)."""
    return jwt.encode(data, settings.secret_key, algorithm=settings.jwt_algorithm)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """Decode and validate the JWT Bearer token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def get_current_rider(token_data: dict = Depends(get_current_user)) -> str:
    """Extract rider_id from token payload."""
    rider_id = token_data.get("sub")
    if not rider_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    return rider_id


async def get_current_driver(token_data: dict = Depends(get_current_user)) -> str:
    """Extract driver_id from token payload."""
    driver_id = token_data.get("sub")
    if not driver_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    return driver_id
