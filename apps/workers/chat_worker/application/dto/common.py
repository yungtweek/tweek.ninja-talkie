from __future__ import annotations
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class MyBaseModel(BaseModel):
    """
    Base Pydantic model configured for camelCase I/O (populate_by_name + alias_generator).
    """
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel
    )
