import time

from fastapi import APIRouter, HTTPException
import httpx

from web.api.models.schemas import TestLLMRequest, TestLLMResponse
from web.api.services import config_service

router = APIRouter(prefix="/api/config", tags=["config"])

VALID_MODULES = [
    "llm", "router", "security", "limits", "workspace",
    "indexer", "retriever", "memory", "tools", "prompts",
    "system_control", "file_organize", "advanced",
]


@router.get("")
def get_all_config():
    return config_service.get_all_config()


@router.get("/{module}")
def get_module_config(module: str):
    if module not in VALID_MODULES:
        raise HTTPException(status_code=404, detail=f"Unknown module: {module}")
    result = config_service.get_module_config(module)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Module not found: {module}")
    return result


@router.put("/{module}")
def update_module_config(module: str, data: dict):
    if module not in VALID_MODULES:
        raise HTTPException(status_code=404, detail=f"Unknown module: {module}")
    errors = config_service.validate_config(module, data)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    result = config_service.update_module_config(module, data)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Module not found: {module}")
    return result


def _resolve_llm_credentials(form_data: dict) -> dict:
    env = config_service.read_env()
    provider = (form_data.get("provider") or env.get("LLM_PROVIDER", "openai")).lower()
    model = form_data.get("model") or env.get("LLM_MODEL", "gpt-4o")
    base_url = form_data.get("base_url") or env.get("LLM_BASE_URL", "https://api.openai.com/v1")

    api_key = form_data.get("api_key", "")
    if config_service.is_masked(api_key) or not api_key:
        api_key = env.get("LLM_API_KEY", "")
    if not base_url or config_service.is_masked(base_url):
        base_url = env.get("LLM_BASE_URL", "https://api.openai.com/v1")

    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
    }


async def _do_test_llm(provider: str, api_key: str, base_url: str, model: str) -> TestLLMResponse:
    start = time.time()
    try:
        if not api_key:
            return TestLLMResponse(success=False, message="API Key 未配置", model=model, latency_ms=0)

        if provider == "anthropic":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": model,
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "Hi"}],
            }
            url = (base_url or "https://api.anthropic.com").rstrip("/") + "/v1/messages"
        else:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model,
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "Hi"}],
            }
            url = (base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            latency_ms = (time.time() - start) * 1000

        if resp.status_code == 200:
            return TestLLMResponse(
                success=True,
                message="Connection successful",
                model=model,
                latency_ms=round(latency_ms, 1),
            )
        else:
            return TestLLMResponse(
                success=False,
                message=f"HTTP {resp.status_code}: {resp.text[:200]}",
                model=model,
                latency_ms=round(latency_ms, 1),
            )
    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        return TestLLMResponse(
            success=False,
            message=str(e)[:200],
            model=model,
            latency_ms=round(latency_ms, 1),
        )


@router.post("/test-llm", response_model=TestLLMResponse)
async def test_llm(req: TestLLMRequest):
    creds = _resolve_llm_credentials({
        "provider": req.provider,
        "api_key": req.api_key,
        "base_url": req.base_url,
        "model": req.model,
    })
    return await _do_test_llm(**creds)


@router.post("/test-llm-current", response_model=TestLLMResponse)
async def test_llm_current():
    env = config_service.read_env()
    creds = _resolve_llm_credentials({
        "provider": env.get("LLM_PROVIDER", "openai"),
        "api_key": env.get("LLM_API_KEY", ""),
        "base_url": env.get("LLM_BASE_URL", ""),
        "model": env.get("LLM_MODEL", "gpt-4o"),
    })
    return await _do_test_llm(**creds)


@router.post("/reload")
def reload_config():
    return config_service.get_all_config()
