"""GPT relay configuration and model discovery for the V3 application.

The relay is configured by V3 directly.  CC Switch is only a convenient
configuration editor and is not a runtime dependency of this service.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


CONFIG_FILENAME = "gpt-relay.json"
SUPPORTED_API_FORMATS = {"responses", "openai_chat_completions"}
DEFAULT_CONFIG: dict[str, Any] = {
    "provider_name": "",
    "base_url": "",
    "api_format": "responses",
    "api_key": "",
    "enabled": False,
    # 默认直连中转站，忽略系统代理（梯子/VPN）。中转站本身就是代理层，
    # 再套一层系统代理常被代理端断开（Unable to connect to proxy）。
    # 个别需要靠代理才能访问的中转站，可在设置里打开此开关。
    "use_system_proxy": False,
    "models": [],
    "models_fetched_at": "",
    "model_routes": {
        "highlight": "",
        "continuous": "",
        "jump": "",
        "review": "",
    },
    "last_test": None,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _config_path() -> Path:
    # Import lazily so this module can be unit-tested without importing the
    # HTTP service at module import time.
    from server import v2_file_service as service

    if service.DATA_ROOT is None:
        raise RuntimeError("需要先配置数据盘")
    path = Path(service.DATA_ROOT) / "系统数据" / CONFIG_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_raw() -> dict[str, Any]:
    path = _config_path()
    if not path.is_file():
        return json.loads(json.dumps(DEFAULT_CONFIG, ensure_ascii=False))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("中转站配置文件无法读取，请检查系统数据目录") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("中转站配置文件格式不正确")
    result = json.loads(json.dumps(DEFAULT_CONFIG, ensure_ascii=False))
    result.update(payload)
    routes = result.get("model_routes")
    result["model_routes"] = {**DEFAULT_CONFIG["model_routes"], **routes} if isinstance(routes, dict) else dict(DEFAULT_CONFIG["model_routes"])
    result["models"] = result["models"] if isinstance(result.get("models"), list) else []
    return result


def _write_raw(payload: dict[str, Any]) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _mask_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "••••••••"
    return f"{api_key[:4]}…{api_key[-4:]}"


def _public_config(raw: dict[str, Any]) -> dict[str, Any]:
    result = dict(raw)
    result.pop("api_key", None)
    result["api_key_set"] = bool(raw.get("api_key"))
    result["api_key_masked"] = _mask_key(str(raw.get("api_key") or ""))
    return result


def get_config() -> dict[str, Any]:
    return _public_config(_read_raw())


def save_config(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("中转站配置必须是对象")
    current = _read_raw()
    provider_name = str(payload.get("provider_name", current.get("provider_name", "")) or "").strip()[:80]
    base_url = str(payload.get("base_url", current.get("base_url", "")) or "").strip().rstrip("/")
    api_format = str(payload.get("api_format", current.get("api_format", "responses")) or "responses")
    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("中转站地址必须是完整的 http(s) 地址")
    if api_format not in SUPPORTED_API_FORMATS:
        raise ValueError("暂不支持该 API 格式")
    api_key_value = payload.get("api_key")
    api_key = str(api_key_value).strip() if api_key_value is not None else str(current.get("api_key") or "")
    # The UI sends an empty key when the user wants to retain the stored key.
    if api_key_value is not None and not api_key:
        api_key = str(current.get("api_key") or "")
    routes_payload = payload.get("model_routes", current.get("model_routes", {}))
    if not isinstance(routes_payload, dict):
        raise ValueError("任务模型分配格式不正确")
    known_models = {str(item.get("id")) for item in current.get("models", []) if isinstance(item, dict)}
    routes: dict[str, str] = {}
    for route_name in DEFAULT_CONFIG["model_routes"]:
        model_id = str(routes_payload.get(route_name, current["model_routes"].get(route_name, "")) or "").strip()
        if model_id and known_models and model_id not in known_models:
            raise ValueError(f"任务模型不在已获取的模型列表中：{model_id}")
        routes[route_name] = model_id
    use_system_proxy = bool(payload.get("use_system_proxy", current.get("use_system_proxy", False)))
    current.update({
        "provider_name": provider_name,
        "base_url": base_url,
        "api_format": api_format,
        "api_key": api_key,
        "enabled": bool(base_url and api_key),
        "use_system_proxy": use_system_proxy,
        "model_routes": routes,
    })
    _write_raw(current)
    return _public_config(current)


def _models_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    return normalized if normalized.endswith("/v1/models") else f"{normalized}/v1/models" if not normalized.endswith("/v1") else f"{normalized}/models"


def _responses_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    return normalized if normalized.endswith("/v1/responses") else f"{normalized}/v1/responses" if not normalized.endswith("/v1") else f"{normalized}/responses"


def _chat_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    return normalized if normalized.endswith("/v1/chat/completions") else f"{normalized}/v1/chat/completions" if not normalized.endswith("/v1") else f"{normalized}/chat/completions"


def _request_json(url: str, api_key: str, body: dict[str, Any] | None = None, timeout: int = 30, use_proxy: bool = False) -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/json", "Authorization": f"Bearer {api_key}"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    try:
        import requests
    except ImportError:
        requests = None
    if requests is not None:
        try:
            with requests.Session() as session:
                # 默认直连：既不读环境变量里的代理，也显式清空 proxies，
                # 避免 Windows 系统代理把中转站请求导去梯子导致 Unable to connect to proxy。
                if not use_proxy:
                    session.trust_env = False
                    session.proxies = {}
                response = session.request("POST" if body is not None else "GET", url, headers=headers, data=data, timeout=timeout)
            try:
                parsed = response.json() if response.content else {}
            except ValueError:
                parsed = {}
            if response.status_code >= 400:
                detail = parsed.get("error") if isinstance(parsed, dict) else None
                message = detail.get("message") if isinstance(detail, dict) else detail or response.reason
                raise RuntimeError(f"中转站请求失败（HTTP {response.status_code}）：{str(message)[:200]}")
            return int(response.status_code), parsed if isinstance(parsed, dict) else {}
        except RuntimeError:
            raise
        except Exception as exc:  # requests exceptions vary by installed version
            raise RuntimeError(f"中转站连接失败：{str(exc)[:200]}") from exc
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if body is not None else "GET")
    if use_proxy:
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    else:
        # 空的 ProxyHandler = 直连，不读系统代理。
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        )
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read()
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
            return int(response.status), parsed if isinstance(parsed, dict) else {}
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            detail = {}
        message = str(detail.get("error", {}).get("message") if isinstance(detail.get("error"), dict) else detail.get("error") or exc.reason)
        raise RuntimeError(f"中转站请求失败（HTTP {exc.code}）：{message[:200]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"中转站连接失败：{str(exc)[:200]}") from exc


def fetch_models() -> dict[str, Any]:
    config = _read_raw()
    base_url = str(config.get("base_url") or "").strip()
    api_key = str(config.get("api_key") or "")
    if not base_url or not api_key:
        raise ValueError("请先填写中转站地址和 API 密钥")
    use_proxy = bool(config.get("use_system_proxy", False))
    _, payload = _request_json(_models_url(base_url), api_key, use_proxy=use_proxy)
    data = payload.get("data")
    if not isinstance(data, list):
        raise RuntimeError("中转站模型列表格式不正确，缺少 data 数组")
    models = []
    for item in data:
        if isinstance(item, dict) and str(item.get("id") or "").strip():
            models.append({"id": str(item["id"]), "owned_by": str(item.get("owned_by") or "")})
    models.sort(key=lambda item: item["id"].lower())
    config["models"] = models
    config["models_fetched_at"] = _now()
    _write_raw(config)
    return _public_config(config)


def test_connection(model: str = "") -> dict[str, Any]:
    config = _read_raw()
    base_url = str(config.get("base_url") or "").strip()
    api_key = str(config.get("api_key") or "")
    if not base_url or not api_key:
        raise ValueError("请先填写中转站地址和 API 密钥")
    selected = str(model or config.get("model_routes", {}).get("highlight") or "").strip()
    if not selected:
        available = config.get("models") or []
        selected = str(available[0].get("id") if available and isinstance(available[0], dict) else "")
    if not selected:
        raise ValueError("请先获取模型列表或指定测试模型")
    use_proxy = bool(config.get("use_system_proxy", False))
    if config.get("api_format") == "openai_chat_completions":
        status, response = _request_json(_chat_url(base_url), api_key, {
            "model": selected,
            "messages": [{"role": "user", "content": "Reply with the single word OK."}],
            "max_tokens": 8,
        }, use_proxy=use_proxy)
    else:
        status, response = _request_json(_responses_url(base_url), api_key, {
            "model": selected,
            "input": "Reply with the single word OK.",
            "max_output_tokens": 8,
        }, use_proxy=use_proxy)
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    result = {"ok": True, "status": status, "model": selected, "usage": usage, "tested_at": _now()}
    config["last_test"] = result
    _write_raw(config)
    return {**result, "config": _public_config(config)}


def _response_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    chunks: list[str] = []
    for item in payload.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if isinstance(content, dict) and content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    if not chunks:
        for choice in payload.get("choices", []) or []:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                chunks.append(message["content"])
    return "".join(chunks).strip()


def generate_json(payload: dict[str, Any]) -> dict[str, Any]:
    """Run one structured JSON request through the configured relay.

    This is the shared model layer for later drama-planning tasks.  It does
    not know anything about episodes or editing.  Local code remains
    responsible for validating the returned ranges against source media.
    """
    if not isinstance(payload, dict):
        raise ValueError("模型请求必须是对象")
    config = _read_raw()
    task_role = str(payload.get("task_role") or "review").strip()
    model = str(payload.get("model") or config.get("model_routes", {}).get(task_role) or "").strip()
    prompt = str(payload.get("prompt") or "").strip()
    schema = payload.get("schema")
    if not model:
        raise ValueError("没有为该任务分配模型")
    if not prompt:
        raise ValueError("模型请求缺少 prompt")
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("结构化请求必须提供 object 类型 JSON Schema")
    stored_models = {str(item.get("id")) for item in config.get("models", []) if isinstance(item, dict)}
    if stored_models and model not in stored_models:
        raise ValueError(f"模型不在当前已获取列表中：{model}")
    base_url = str(config.get("base_url") or "").strip()
    api_key = str(config.get("api_key") or "")
    if not base_url or not api_key:
        raise ValueError("请先填写中转站地址和 API 密钥")
    effort = str(payload.get("reasoning_effort") or "medium").strip()
    timeout_s = max(30, min(900, int(payload.get("timeout_s") or 120)))
    use_proxy = bool(config.get("use_system_proxy", False))
    started = time.monotonic()
    if config.get("api_format") == "openai_chat_completions":
        request_body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_schema", "json_schema": {"name": str(payload.get("schema_name") or "structured_result"), "strict": True, "schema": schema}},
            "max_tokens": int(payload.get("max_output_tokens") or 4000),
        }
        status, response = _request_json(_chat_url(base_url), api_key, request_body, timeout=timeout_s, use_proxy=use_proxy)
    else:
        request_body = {
            "model": model,
            "input": prompt,
            "reasoning": {"effort": effort},
            "text": {"format": {"type": "json_schema", "name": str(payload.get("schema_name") or "structured_result"), "strict": True, "schema": schema}},
        }
        if payload.get("max_output_tokens"):
            request_body["max_output_tokens"] = int(payload["max_output_tokens"])
        status, response = _request_json(_responses_url(base_url), api_key, request_body, timeout=timeout_s, use_proxy=use_proxy)
    elapsed = round(time.monotonic() - started, 3)
    output_text = _response_text(response)
    if not output_text:
        raise RuntimeError("中转站未返回结构化文本")
    try:
        data = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("中转站返回的内容不是合法JSON") from exc
    if not isinstance(data, dict):
        raise RuntimeError("中转站返回的JSON不是对象")
    result = {
        "ok": True,
        "status": status,
        "task_role": task_role,
        "model": model,
        "data": data,
        "usage": response.get("usage") if isinstance(response.get("usage"), dict) else {},
        "elapsed_s": elapsed,
        "created_at": _now(),
    }
    config["last_request"] = {key: result[key] for key in ("task_role", "model", "status", "usage", "elapsed_s", "created_at")}
    _write_raw(config)
    return result

