"""Versioned system-role defaults. No implicit wildcard permissions."""

from enum import StrEnum


class RoleCode(StrEnum):
    EMPLOYEE = "EMPLOYEE"
    TECHNICIAN = "TECHNICIAN"
    IT_MANAGER = "IT_MANAGER"
    ADMIN = "ADMIN"


PERMISSIONS = frozenset(
    [
        "user:view",
        "user:create",
        "user:update",
        "user:disable",
        "role:view",
        "role:manage",
        "permission:view",
        "permission:manage",
        "department:view",
        "department:manage",
        "location:view",
        "location:manage",
        "ticket:create",
        "ticket:view_own",
        "ticket:view_team",
        "ticket:view_all",
        "ticket:update",
        "ticket:assign",
        "ticket:reassign",
        "ticket:comment",
        "ticket:internal_note",
        "ticket:escalate",
        "ticket:resolve",
        "ticket:close",
        "ticket:reopen",
        "incident:view",
        "incident:create",
        "incident:update",
        "incident:resolve",
        "problem:view",
        "problem:create",
        "problem:update",
        "problem:resolve",
        "change:view",
        "change:create",
        "change:update",
        "change:approve",
        "asset:view_own",
        "asset:view_team",
        "asset:view_all",
        "asset:create",
        "asset:update",
        "asset:retire",
        "knowledge:view",
        "knowledge:create",
        "knowledge:update",
        "knowledge:review",
        "knowledge:publish",
        "knowledge:archive",
        "sla:view",
        "sla:manage",
        "alert:view",
        "alert:acknowledge",
        "alert:resolve",
        "alert:manage",
        "analytics:view",
        "audit:view",
        "ai:use",
        "ai:configure",
        "monitoring:view",
        "monitoring:manage",
        "system:configure",
        "team:view",
        "team:manage",
    ]
)

EMPLOYEE = frozenset(
    [
        "ticket:create",
        "ticket:view_own",
        "ticket:comment",
        "ticket:reopen",
        "asset:view_own",
        "knowledge:view",
    ]
)
TECHNICIAN = EMPLOYEE | frozenset(
    [
        "ticket:view_team",
        "ticket:update",
        "ticket:assign",
        "ticket:reassign",
        "ticket:internal_note",
        "ticket:escalate",
        "ticket:resolve",
        "ticket:close",
        "incident:view",
        "incident:create",
        "incident:update",
        "incident:resolve",
        "problem:view",
        "problem:create",
        "problem:update",
        "change:view",
        "change:create",
        "change:update",
        "asset:view_team",
        "knowledge:create",
        "knowledge:update",
        "sla:view",
        "alert:view",
        "alert:acknowledge",
        "alert:resolve",
        "analytics:view",
        "ai:use",
        "monitoring:view",
        "team:view",
        "department:view",
        "location:view",
    ]
)
MANAGER = TECHNICIAN | frozenset(
    [
        "ticket:view_all",
        "asset:view_all",
        "problem:resolve",
        "change:approve",
        "knowledge:review",
        "knowledge:publish",
        "knowledge:archive",
        "team:manage",
    ]
)
ROLE_PERMISSIONS: dict[RoleCode, frozenset[str]] = {
    RoleCode.EMPLOYEE: EMPLOYEE,
    RoleCode.TECHNICIAN: TECHNICIAN,
    RoleCode.IT_MANAGER: MANAGER,
    RoleCode.ADMIN: PERMISSIONS,
}
