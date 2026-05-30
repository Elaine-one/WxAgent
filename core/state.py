from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages


class PlanStep(TypedDict):
    step: int
    description: str
    tool: str
    args: dict
    status: Literal["pending", "running", "done", "failed", "skipped"]
    depends_on: list[int]


class AgentState(TypedDict):
    user_id: str
    task_id: str

    messages: Annotated[list[dict], add_messages]
    user_input: str

    plan: list[PlanStep]
    current_step: int

    retry_counts: dict[int, int]
    last_error: str

    pending_confirmation: dict
    confirmation_response: str

    interrupted: bool
    interrupted_message: str

    msg_type: str
    _reflector_decision: str

    final_response: str
    task_complete: bool

    messages_window: int
    user_preferences: dict[str, str]
    active_tools: list[str]
    cost: dict
    image_urls: list[str]
    image_media_refs: list[dict]
    image_description: str
