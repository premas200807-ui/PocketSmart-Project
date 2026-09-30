"""
models.py - Input/output schemas for PocketSmart AI
(Pydantic models used by the FastAPI routes)
"""
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Auth / user models
# ---------------------------------------------------------------------------
class RegisterUser(BaseModel):
    username: str = Field(..., min_length=3, max_length=30)
    email: str
    full_name: Optional[str] = None
    password: str = Field(..., min_length=6)


class User(BaseModel):
    username: str
    email: str
    full_name: Optional[str] = None
    disabled: bool = False


class UserInDB(User):
    hashed_password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class UserSession(BaseModel):
    username: str
    login_time: datetime
    last_activity: datetime
    token: str
    user_data: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Planner input models
# ---------------------------------------------------------------------------
class HomeBudgetInput(BaseModel):
    total_budget: float = Field(..., gt=0, description="Total budget in INR")
    num_lights: int = Field(0, ge=0, le=100)
    num_fans: int = Field(0, ge=0, le=50)
    num_furniture: int = Field(0, ge=0, le=100)
    num_dining_tables: int = Field(0, ge=0, le=10)
    has_living_room: bool = True
    has_kitchen: bool = False
    has_bedroom: bool = False
    additional_requirements: Optional[str] = None


class PartyBudgetInput(BaseModel):
    total_budget: float = Field(..., gt=0, description="Total budget in INR")
    party_type: str = Field(..., min_length=2)
    num_guests: int = Field(..., gt=0, le=5000)
    venue_type: Optional[str] = None
    needs_catering: bool = True
    needs_decoration: bool = True
    needs_entertainment: bool = False
    additional_requirements: Optional[str] = None


class JewelryBudgetInput(BaseModel):
    total_budget: float = Field(..., gt=0, description="Total budget in INR")
    occasion: str = Field(..., min_length=2)
    preferences: Optional[str] = None


# ---------------------------------------------------------------------------
# History model
# ---------------------------------------------------------------------------
class RecommendationHistory(BaseModel):
    id: str
    username: str
    timestamp: str
    recommendation_type: str          # "home" | "party" | "jewelry"
    input_summary: Dict[str, Any]
    result_summary: Dict[str, Any]
    full_result: Dict[str, Any]
