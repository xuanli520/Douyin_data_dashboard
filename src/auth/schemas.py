from datetime import datetime
from typing import Literal

from fastapi_users import schemas
from pydantic import BaseModel, ConfigDict, Field


class UserRead(schemas.BaseUser[int]):
    username: str
    gender: str | None = None
    phone: str | None = None
    department: str | None = None


class UserCreate(schemas.BaseUserCreate):
    username: str
    gender: str | None = None
    phone: str | None = None
    department: str | None = None


class UserUpdate(schemas.BaseUserUpdate):
    username: str | None = None
    gender: str | None = None
    phone: str | None = None
    department: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"


class MessageResponse(BaseModel):
    detail: str


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None = None
    is_system: bool
    created_at: datetime
    updated_at: datetime


class RoleCreate(BaseModel):
    name: str = Field(..., max_length=100)
    description: str | None = Field(None, max_length=255)


class RoleUpdate(BaseModel):
    name: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=255)


class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    description: str | None = None
    module: str
    created_at: datetime
    updated_at: datetime


class RoleWithPermissions(RoleRead):
    permissions: list[PermissionRead]


class PermissionAssign(BaseModel):
    permission_ids: list[int] = Field(default_factory=list)


class UserListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str
    is_active: bool
    is_superuser: bool
    is_verified: bool
    gender: str | None = None
    phone: str | None = None
    department: str | None = None
    created_at: datetime
    updated_at: datetime
    roles: list[RoleRead] = Field(default_factory=list)


class UserCreateByAdmin(BaseModel):
    username: str = Field(..., max_length=50)
    email: str = Field(..., max_length=320)
    password: str = Field(..., min_length=8, max_length=128)
    gender: str | None = Field(None, max_length=20)
    phone: str | None = Field(None, max_length=20)
    department: str | None = Field(None, max_length=100)
    role_ids: list[int] = Field(default_factory=list)


class UserUpdateByAdmin(BaseModel):
    username: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=320)
    password: str | None = Field(None, min_length=8, max_length=128)
    is_active: bool | None = None
    is_superuser: bool | None = None
    is_verified: bool | None = None
    gender: str | None = Field(None, max_length=20)
    phone: str | None = Field(None, max_length=20)
    department: str | None = Field(None, max_length=100)
    role_ids: list[int] | None = None


class AssignRolesRequest(BaseModel):
    role_ids: list[int] = Field(default_factory=list)


class UserStatsResponse(BaseModel):
    total: int
    active: int
    inactive: int
    superusers: int
