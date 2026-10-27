from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BookingCreate(BaseModel):
    event_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=10)


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    event_id: int
    quantity: int
    total_price: int
    status: str
    created_at: datetime


class BookingPage(BaseModel):
    items: list[BookingRead]
    total: int
    limit: int
    offset: int
