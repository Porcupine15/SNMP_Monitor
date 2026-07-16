from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_roles
from app.lab import get_profile, list_profiles
from app.models import User

router = APIRouter(prefix="/api/lab", tags=["lab"])


@router.get("/profiles")
def profiles(current_user: User = Depends(require_roles("admin", "operator", "viewer"))):
    return {"items": list_profiles()}


@router.get("/profiles/{profile_id}")
def profile(profile_id: str, current_user: User = Depends(require_roles("admin", "operator", "viewer"))):
    data = get_profile(profile_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Lab profile not found")
    return data
