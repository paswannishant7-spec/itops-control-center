from datetime import datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.modules.access.catalog import RoleCode
from app.modules.directory.models import DirectoryStatus, TeamMemberRole
from app.modules.identity.models import UserStatus

Code = Annotated[str, Field(min_length=2, max_length=32, pattern=r"^[A-Z][A-Z0-9_-]*$")]
Name = Annotated[str, Field(min_length=2, max_length=160)]
Reason = Annotated[str, Field(min_length=3, max_length=500)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReferenceSummary(StrictModel):
    id: UUID
    code: str
    name: str


class DepartmentCreate(StrictModel):
    code: Code
    name: Name
    description: str | None = Field(default=None, max_length=500)
    reason: Reason

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class DepartmentUpdate(StrictModel):
    name: Name | None = None
    description: str | None = Field(default=None, max_length=500)
    status: DirectoryStatus | None = None
    reason: Reason

    @model_validator(mode="after")
    def require_change(self) -> "DepartmentUpdate":
        if not ({"name", "description", "status"} & self.model_fields_set):
            raise ValueError("At least one department field must be supplied")
        return self


class DepartmentResponse(StrictModel):
    id: UUID
    code: str
    name: str
    description: str | None
    status: str
    user_count: int
    team_count: int
    created_at: datetime
    updated_at: datetime


class LocationCreate(StrictModel):
    code: Code
    name: Name
    timezone: str = Field(min_length=1, max_length=64)
    address: str | None = Field(default=None, max_length=500)
    reason: Reason

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Timezone must be a valid IANA identifier") from exc
        return value


class LocationUpdate(StrictModel):
    name: Name | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    address: str | None = Field(default=None, max_length=500)
    status: DirectoryStatus | None = None
    reason: Reason

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Timezone must be a valid IANA identifier") from exc
        return value

    @model_validator(mode="after")
    def require_change(self) -> "LocationUpdate":
        if not ({"name", "timezone", "address", "status"} & self.model_fields_set):
            raise ValueError("At least one location field must be supplied")
        return self


class LocationResponse(StrictModel):
    id: UUID
    code: str
    name: str
    timezone: str
    address: str | None
    status: str
    user_count: int
    team_count: int
    created_at: datetime
    updated_at: datetime


class TeamCreate(StrictModel):
    code: Code
    name: Name
    description: str | None = Field(default=None, max_length=500)
    department_id: UUID | None = None
    location_id: UUID | None = None
    reason: Reason

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class TeamUpdate(StrictModel):
    name: Name | None = None
    description: str | None = Field(default=None, max_length=500)
    department_id: UUID | None = None
    location_id: UUID | None = None
    status: DirectoryStatus | None = None
    reason: Reason

    @model_validator(mode="after")
    def require_change(self) -> "TeamUpdate":
        fields = {"name", "description", "department_id", "location_id", "status"}
        if not (fields & self.model_fields_set):
            raise ValueError("At least one team field must be supplied")
        return self


class TeamResponse(StrictModel):
    id: UUID
    code: str
    name: str
    description: str | None
    status: str
    department: ReferenceSummary | None
    location: ReferenceSummary | None
    member_count: int
    created_at: datetime
    updated_at: datetime


class TeamMemberRequest(StrictModel):
    member_role: TeamMemberRole = TeamMemberRole.MEMBER
    reason: Reason


class TeamMemberRemoval(StrictModel):
    reason: Reason


class TeamMemberResponse(StrictModel):
    user_id: UUID
    display_name: str
    email: EmailStr
    job_title: str | None
    status: str
    member_role: str
    roles: list[str]


class TeamDetailResponse(TeamResponse):
    members: list[TeamMemberResponse]


class TechnicianCandidate(StrictModel):
    id: UUID
    display_name: str
    email: EmailStr
    job_title: str | None
    roles: list[str]


class UserCreate(StrictModel):
    email: EmailStr
    display_name: Name
    initial_password: str = Field(min_length=12, max_length=128)
    employee_number: str | None = Field(default=None, min_length=1, max_length=64)
    job_title: str | None = Field(default=None, max_length=120)
    department_id: UUID | None = None
    location_id: UUID | None = None
    roles: list[RoleCode] = Field(
        default_factory=lambda: [RoleCode.EMPLOYEE], min_length=1, max_length=4
    )
    reason: Reason


class UserUpdate(StrictModel):
    email: EmailStr | None = None
    display_name: Name | None = None
    employee_number: str | None = Field(default=None, min_length=1, max_length=64)
    job_title: str | None = Field(default=None, max_length=120)
    department_id: UUID | None = None
    location_id: UUID | None = None
    reason: Reason

    @model_validator(mode="after")
    def require_change(self) -> "UserUpdate":
        fields = {
            "email",
            "display_name",
            "employee_number",
            "job_title",
            "department_id",
            "location_id",
        }
        if not (fields & self.model_fields_set):
            raise ValueError("At least one user field must be supplied")
        return self


class UserStatusUpdate(StrictModel):
    status: UserStatus
    reason: Reason


class UserDirectoryResponse(StrictModel):
    id: UUID
    email: EmailStr
    display_name: str
    employee_number: str | None
    job_title: str | None
    status: str
    department: ReferenceSummary | None
    location: ReferenceSummary | None
    roles: list[str]
    teams: list[ReferenceSummary]
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserPage(StrictModel):
    items: list[UserDirectoryResponse]
    total: int
    offset: int
    limit: int
