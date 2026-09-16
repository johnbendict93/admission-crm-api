from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from supabase_auth.errors import AuthApiError

from app.core.config import settings
from app.core.database import get_supabase_auth_client, get_supabase_client
from app.models.auth import LoginRequest, LoginResponse, UserOut

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    credentials: LoginRequest,
    auth_client: Client = Depends(get_supabase_auth_client),
    supabase: Client = Depends(get_supabase_client),
):
    """Authenticates against real Supabase Auth (sign_in_with_password) -
    confirmed live and wired on this project via the handle_new_auth_user()
    trigger - and returns the resulting access token plus this project's
    own app-level user record (role, full_name), since Supabase Auth itself
    has no concept of admin/counselor/staff/viewer.
    """
    try:
        result = auth_client.auth.sign_in_with_password(
            {"email": credentials.email, "password": credentials.password}
        )
    except AuthApiError:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not result.session or not result.user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user_row = (
        supabase.table(settings.USERS_TABLE)
        .select("id, email, full_name, role")
        .eq("id", result.user.id)
        .limit(1)
        .execute()
    )
    if not user_row.data:
        raise HTTPException(
            status_code=401,
            detail="Authenticated with Supabase Auth, but no matching row exists in the users table",
        )

    return LoginResponse(
        access_token=result.session.access_token,
        user=UserOut(**user_row.data[0]),
    )
