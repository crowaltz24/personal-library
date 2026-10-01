from pydantic import BaseModel, Field


class AuthRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=200)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int