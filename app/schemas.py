from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

Plan = Literal["basic", "premium"]
LineStatus = Literal["pending", "active", "suspended"]
EventType = Literal["activated", "suspended", "reactivated"]


class LineCreate(BaseModel):
    line_id: str = Field(min_length=1, examples=["L-100"])
    employee_name: str = Field(min_length=1, examples=["Ana López"])
    phone_number: str = Field(pattern=r"^\+?\d{10,15}$", examples=["5512345678"])
    plan: Plan


class LineUpdate(BaseModel):
    plan: Plan


class LineOut(BaseModel):
    line_id: str
    company_id: str
    employee_name: str
    phone_number: str
    plan: Plan
    status: LineStatus


class NetworkEvent(BaseModel):
    event_id: str = Field(min_length=1)
    line_id: str = Field(min_length=1)
    type: EventType
    timestamp: AwareDatetime


class NetworkEventResult(BaseModel):
    event_id: str
    result: Literal["applied", "duplicate", "ignored_out_of_order"]
    line_status: LineStatus


class BenefitOut(BaseModel):
    """Public view of a benefit. The code is intentionally absent: only redemption reveals it."""

    id: str
    category: str
    merchant: str
    description: str
    valid_until: str | None


class RedemptionOut(BaseModel):
    benefit_id: str
    code: str
    period: str


class AgentQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class AgentAnswer(BaseModel):
    answer: str
    benefits: list[BenefitOut]
