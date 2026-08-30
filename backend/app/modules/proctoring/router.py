from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.db.models import ProctoringProfile
from app.modules.schemas import ProctoringProfileCreate, ProctoringProfileOut

router = APIRouter(prefix="/proctoring-profiles", tags=["proctoring"])


@router.get("", response_model=list[ProctoringProfileOut])
def list_profiles(
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_roles("admin", "instructor", "student")),
) -> list[ProctoringProfile]:
    return list(db.scalars(select(ProctoringProfile).order_by(ProctoringProfile.name.asc())).all())


@router.get("/{profile_id}", response_model=ProctoringProfileOut)
def get_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_roles("admin", "instructor", "student")),
) -> ProctoringProfile:
    profile = db.get(ProctoringProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Proctoring profile not found")
    return profile


@router.post("", response_model=ProctoringProfileOut, status_code=status.HTTP_201_CREATED)
def create_profile(
    body: ProctoringProfileCreate,
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_roles("admin", "instructor")),
) -> ProctoringProfile:
    profile = ProctoringProfile(
        name=body.name,
        strictness=body.strictness,
        warn_threshold=body.warn_threshold,
        flag_threshold=body.flag_threshold,
        terminate_threshold=body.terminate_threshold,
        require_android_camera=body.require_android_camera,
        blacklist_apps_csv=body.blacklist_apps_csv,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.put("/{profile_id}", response_model=ProctoringProfileOut)
def update_profile(
    profile_id: str,
    body: ProctoringProfileCreate,
    db: Session = Depends(get_db),
    _claims: dict = Depends(require_roles("admin", "instructor")),
) -> ProctoringProfile:
    profile = db.get(ProctoringProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Proctoring profile not found")
    profile.name = body.name
    profile.strictness = body.strictness
    profile.warn_threshold = body.warn_threshold
    profile.flag_threshold = body.flag_threshold
    profile.terminate_threshold = body.terminate_threshold
    profile.require_android_camera = body.require_android_camera
    profile.blacklist_apps_csv = body.blacklist_apps_csv
    db.commit()
    db.refresh(profile)
    return profile
