"""Shapes of what the models return. llm.py passes these to OpenAI's structured outputs, so the
API is held to the schema and a malformed reply fails there instead of halfway through a run."""
from pydantic import BaseModel


class Step(BaseModel):
    tag: str
    args: list[str | int | float]
    description: str
    undo_tag: str | None
    conditions: list[str]
    requires_confirmation: bool
    visible_effect: str


class Plan(BaseModel):
    steps: list[Step]


class StepCheck(BaseModel):
    action_completed: bool
    issue: str | None
    current_screen_state: str
