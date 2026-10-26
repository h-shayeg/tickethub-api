from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    starts_at: AwareDatetime
    price: int = Field(ge=0)
    total_tickets: int = Field(gt=0)


class EventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    starts_at: AwareDatetime | None = None
    price: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def reject_null_for_required_fields(self):
        for name in ("title", "starts_at", "price"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    starts_at: datetime
    price: int
    total_tickets: int
    available_tickets: int
    created_at: datetime


class EventPage(BaseModel):
    items: list[EventRead]
    total: int
    limit: int
    offset: int
