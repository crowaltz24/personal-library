from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SyncMutation(BaseModel):
    client_mutation_id: str = Field(min_length=1, max_length=100)
    entity_type: Literal["library_entry"]
    entity_id: int | None = None
    operation: Literal["create", "update", "delete"]
    base_version: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SyncPushRequest(BaseModel):
    mutations: list[SyncMutation] = Field(default_factory=list, max_length=100)


class SyncChangeResponse(BaseModel):
    revision: int
    entity_type: str
    entity_id: int
    operation: str
    version: int
    payload: dict[str, Any]
    created_at: datetime


class SyncPushResponse(BaseModel):
    results: list[SyncChangeResponse]
    revision: int


class SyncPullResponse(BaseModel):
    changes: list[SyncChangeResponse]
    revision: int