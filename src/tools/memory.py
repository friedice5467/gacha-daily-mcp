from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryGetInput(BaseModel):
    key: str = Field(description="Key to retrieve from task memory")


class MemorySetInput(BaseModel):
    key: str = Field(description="Key to store in task memory")
    value: str = Field(description="Value to store")


class MemoryDeleteInput(BaseModel):
    key: str = Field(description="Key to delete from task memory")


class MemoryListInput(BaseModel):
    pass


MEMORY_GET_TOOL = {
    "name": "memory_get",
    "description": "Retrieve a value from persistent task memory by key.",
    "parameters": MemoryGetInput.model_json_schema(),
}

MEMORY_SET_TOOL = {
    "name": "memory_set",
    "description": "Store a key-value pair in persistent task memory.",
    "parameters": MemorySetInput.model_json_schema(),
}

MEMORY_DELETE_TOOL = {
    "name": "memory_delete",
    "description": "Delete a key from persistent task memory.",
    "parameters": MemoryDeleteInput.model_json_schema(),
}

MEMORY_LIST_TOOL = {
    "name": "memory_list",
    "description": "List all keys in persistent task memory.",
    "parameters": MemoryListInput.model_json_schema(),
}

MEMORY_TOOLS = [MEMORY_GET_TOOL, MEMORY_SET_TOOL, MEMORY_DELETE_TOOL, MEMORY_LIST_TOOL]
