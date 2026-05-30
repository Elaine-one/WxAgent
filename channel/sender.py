import json
import secrets

import httpx

from channel.client import (
    DEFAULT_API_TIMEOUT_S, ITEM_TYPE_TEXT, _build_base_info, _build_headers,
)


def send_message(state, to_user: str, text: str) -> str:
    client_id = f"bot-{secrets.token_hex(8)}"
    ctx_token = state.context_tokens.get(to_user, "")

    url = f"{state.base_url}/ilink/bot/sendmessage"
    body = json.dumps({
        "msg": {
            "from_user_id": "",
            "to_user_id": to_user,
            "client_id": client_id,
            "message_type": 2,
            "message_state": 2,
            "item_list": [
                {"type": ITEM_TYPE_TEXT, "text_item": {"text": text}}
            ],
            "context_token": ctx_token,
        },
        "base_info": _build_base_info(),
    })
    h = _build_headers(token=state.token)
    resp = httpx.post(url, content=body, headers=h, timeout=DEFAULT_API_TIMEOUT_S)
    resp.raise_for_status()
    return client_id
