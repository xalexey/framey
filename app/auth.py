from fastapi import Header, HTTPException

from app.database import get_user_by_api_key


def get_current_user(x_api_key: str = Header(...)) -> dict:
    user = get_user_by_api_key(x_api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user
