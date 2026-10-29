"""Low-cost, opt-in local AI backends. Standard library only; no cloud provisioning.

Each API endpoint is intentionally bound to the loopback interface, suitable for
SSH/Tailscale tunnels. Never point these adapters at untrusted URLs.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
import json
import os
import platform
import shutil
import urllib.request
from urllib.parse import urlsplit

CATALOG = Path(__file__).resolve().parents[1] / "config" / "ai-stack-catalog.json"


def catalog() -> list[dict]:
    return json.loads(CATALOG.read_text(encoding="utf-8"))["components"]


def _money(value: str | float | int, name: str) -> Decimal:
    try:
        num = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{name}: invalid number") from exc
    if not num.is_finite() or num < 0:
        raise ValueError(f"{name}: must be finite and non-negative")
    return num


def estimate_cost(hours: float, hourly_usd: float, stored_gb: float = 0,
                  storage_monthly_usd_per_gb: float = 0) -> dict:
    """An estimate, NOT a spending cap or provider quote."""
    h = _money(hours, "hours")
    rate = _money(hourly_usd, "hourly_usd")
    gb = _money(stored_gb, "stored_gb")
    storage_rate = _money(storage_monthly_usd_per_gb, "storage_monthly_usd_per_gb")
    compute = h * rate
    storage = gb * storage_rate
    return {"compute_usd": str(compute.quantize(Decimal("0.01"))),
            "storage_usd": str(storage.quantize(Decimal("0.01"))),
            "estimated_total_usd": str((compute + storage).quantize(Decimal("0.01"))),
            "warning": "Not a hard cap; excludes network, taxes, idle VM and other costs."}


def machine_status() -> dict:
    usage = shutil.disk_usage("/")
    return {"architecture": platform.machine(), "os": platform.system(),
            "disk_free_gb": round(usage.free / 1024**3, 2),
            "gpu_submission_enabled": os.getenv("BELENTANI_GPU_SUBMIT_ENABLED") == "1",
            "ace_step_configured": bool(os.getenv("BELENTANI_ACE_URL")),
            "comfyui_configured": bool(os.getenv("BELENTANI_COMFY_URL"))}


def _loopback_url(env_name: str, fallback: str) -> str:
    raw = os.getenv(env_name, fallback).rstrip("/")
    parsed = urlsplit(raw)
    if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "[::1]", "::1"}
        or parsed.username or parsed.password or parsed.path not in {"", "/"}
        or parsed.query or parsed.fragment):
        raise ValueError(f"{env_name} must be a loopback HTTP URL (use an SSH tunnel)")
    return raw


def _json_api(url: str, payload: dict | None = None, *, timeout: int = 15,
              token: str = "") -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=body, headers=headers,
                                 method="POST" if body is not None else "GET")
    # Do not follow redirects to other hosts (avoids loopback -> external SSRF).
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ValueError("API redirects are disabled")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
    with opener.open(req, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"Backend returned HTTP {response.status}")
        data = response.read(1_000_001)
    if len(data) > 1_000_000:
        raise ValueError("Backend response exceeds 1 MB")
    result = json.loads(data)
    if not isinstance(result, dict):
        raise ValueError("Expected JSON object from backend")
    return result


def _submission_gate(estimated_hours: float) -> dict:
    h = _money(estimated_hours, "estimated_hours")
    if h <= 0:
        raise ValueError("estimated_hours must be positive")
    rate = _money(os.getenv("BELENTANI_GPU_RATE_USD_H", "0"), "GPU_RATE")
    max_usd = _money(os.getenv("BELENTANI_GPU_MAX_ESTIMATED_USD", "0"), "GPU_MAX_ESTIMATED")
    if rate <= 0 or max_usd <= 0:
        raise ValueError("Set positive GPU rate and estimated job budget before submission")
    amount = h * rate
    if amount > max_usd:
        raise ValueError("Estimated GPU cost exceeds approved per-job budget")
    return {"estimated_usd": str(amount.quantize(Decimal("0.01"))),
            "warning": "Estimated-only check; does not shut down or cap cloud billing."}


def _is_enabled() -> bool:
    return os.getenv("BELENTANI_GPU_SUBMIT_ENABLED") == "1"


def create_music(prompt: str, lyrics: str = "", duration_s: int = 60,
                 bpm: int = 120, estimated_hours: float = 0.1) -> dict:
    """Submit to a *running local/tunneled* ACE-Step REST API, or dry-run."""
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 2000:
        raise ValueError("prompt must be 1..2000 characters")
    if not isinstance(lyrics, str) or len(lyrics) > 12000:
        raise ValueError("lyrics exceeds 12000 characters")
    if type(duration_s) is not int or not 10 <= duration_s <= 600:
        raise ValueError("duration_s must be an integer from 10 to 600")
    if type(bpm) is not int or not 30 <= bpm <= 300:
        raise ValueError("bpm must be an integer from 30 to 300")
    payload = {"prompt": prompt, "lyrics": lyrics, "audio_duration": duration_s,
               "bpm": bpm, "inference_steps": 8, "batch_size": 1}
    if not _is_enabled():
        return {"status": "dry-run", "backend": "ACE-Step 1.5", "payload": payload,
                "notice": "No API call, GPU provisioning, or charge occurred."}
    budget = _submission_gate(estimated_hours)
    host = _loopback_url("BELENTANI_ACE_URL", "http://127.0.0.1:8001")
    result = _json_api(host + "/release_task", payload,
                       token=os.getenv("BELENTANI_ACE_API_KEY", ""))
    return {"status": "submitted", "backend_response": result, **budget}


def music_status(task_id: str) -> dict:
    if not isinstance(task_id, str) or len(task_id) > 128 or not task_id:
        raise ValueError("Invalid task_id")
    host = _loopback_url("BELENTANI_ACE_URL", "http://127.0.0.1:8001")
    return _json_api(host + "/query_result", {"task_id_list": [task_id]},
                     token=os.getenv("BELENTANI_ACE_API_KEY", ""))


def submit_video(workflow_name: str, estimated_hours: float = 0.25) -> dict:
    """Submit a reviewed ComfyUI API JSON graph from a fixed directory."""
    if not isinstance(workflow_name, str) or not workflow_name.endswith(".json") or workflow_name != Path(workflow_name).name:
        raise ValueError("Provide only a basename ending .json")
    base = Path(os.getenv("BELENTANI_WORKFLOW_DIR", str(Path.home() / "ai-workflows"))).resolve()
    path = (base / workflow_name).resolve()
    if not path.is_relative_to(base) or not path.is_file() or path.stat().st_size > 1_000_000:
        raise ValueError("Missing/out-of-bounds workflow or file exceeds 1 MB")
    graph = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(graph, dict) or not graph:
        raise ValueError("Workflow must be a nonempty API-format JSON graph")
    if not _is_enabled():
        return {"status": "dry-run", "backend": "ComfyUI", "workflow": workflow_name,
                "nodes": len(graph), "notice": "No API call or GPU charge occurred."}
    budget = _submission_gate(estimated_hours)
    host = _loopback_url("BELENTANI_COMFY_URL", "http://127.0.0.1:8188")
    result = _json_api(host + "/prompt", {"prompt": graph}, timeout=30)
    return {"status": "submitted", "backend_response": result, **budget}


def video_status(prompt_id: str) -> dict:
    import uuid
    try:
        value = str(uuid.UUID(prompt_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("prompt_id must be a UUID") from exc
    host = _loopback_url("BELENTANI_COMFY_URL", "http://127.0.0.1:8188")
    return _json_api(host + "/history/" + value)


def cpu_llm_status() -> dict:
    host = _loopback_url("BELENTANI_LLAMA_URL", "http://127.0.0.1:8080")
    return _json_api(host + "/health", timeout=5)
