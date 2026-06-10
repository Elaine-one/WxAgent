from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    user_id: str
    task_id: str

    messages: Annotated[list[dict], add_messages]
    user_input: str

    last_error: str

    pending_confirmation: dict
    confirmation_response: str

    interrupted: bool
    interrupted_message: str

    msg_type: str

    final_response: str
    task_complete: bool

    messages_window: int
    user_preferences: dict[str, str]
    active_tools: list[str]
    cost: dict
    image_urls: list[str]
    image_media_refs: list[dict]
    image_description: str
    memory_context: str
    confirm_rounds: int
    saved_image_paths: list[str]
    file_urls: list[str]
    file_media_refs: list[dict]
    file_names: list[str]
    file_sizes: list[int]
    saved_file_paths: list[str]
    voice_urls: list[str]
    voice_media_refs: list[dict]
    voice_transcription: str
    video_urls: list[str]
    video_media_refs: list[dict]
    candidate_skill_names: list[str]
