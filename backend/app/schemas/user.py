from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    id: int
    clerk_user_id: str
    email: str | None
    name: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class UserOut(BaseModel):
    id: int
    clerk_user_id: str
    email: str
    name: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)