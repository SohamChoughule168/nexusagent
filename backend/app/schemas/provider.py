"""Schemas for the providers status/configuration API."""
from typing import List, Optional

from pydantic import BaseModel


class ProviderInfo(BaseModel):
    name: str
    label: str
    description: str
    requires_key: bool
    configured: bool
    active: bool = False


class ProvidersResponse(BaseModel):
    active_llm: str
    active_embeddings: str
    llm_providers: List[ProviderInfo]
    embedding_providers: List[ProviderInfo]
