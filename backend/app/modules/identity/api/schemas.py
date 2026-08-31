from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    password_rotation_required: bool = False


class PasswordRotationRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    permissions: list[str]

    @field_validator("permissions", mode="before")
    @classmethod
    def flatten_permissions(cls, v):
        """Accepts either a list of Permission ORM objects (with `.code`)
        or an already-flat list of strings."""
        return [p.code if hasattr(p, "code") else p for p in v]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    email: EmailStr
    full_name: str
    is_active: bool
    role: RoleRead


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)
    role_name: str


class UserUpdateRole(BaseModel):
    role_name: str


class UserInvite(BaseModel):
    email: EmailStr
    full_name: str
    role_name: str
