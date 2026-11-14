"""One door for every model call: routing by tier, JSON output, disk cache, usage log.

Tiers: 'fast' for bulk extraction and classification, 'strong' for the reasoning steps of the debate.
Identical prompts are answered from disk, so re-running research on a company costs nothing.
"""
import hashlib
import json
import os
import re
import threading
import time

from . import store
from .config import CACHE, FALLBACK_MODEL, FAST_MODEL, MODEL_CHOICES, STRONG_MODEL

_KEY_FOR_PREFIX = {
    "gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY", "claude": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY", "mistral": "MISTRAL_API_KEY",
}
_usage_lock = threading.Lock()
used_models = {}   # tier -> names of the models that actually answered (the fallback may have stepped in)
_down_until = {}   # model -> time until which it is skipped after an outage
usage = {"calls": 0, "cache_hits": 0, "input_tokens": 0, "output_tokens": 0, "by_model": {}}


def model_for(tier: str) -> str:
    return STRONG_MODEL if tier == "strong" else FAST_MODEL


def _has_key(model: str) -> bool:
    prefix = re.split(r"[/-]", model)[0]
    if prefix == "ollama":
        return True
    key = _KEY_FOR_PREFIX.get(prefix)
    return bool(key and os.getenv(key))


def _fallbacks() -> list[str]:
    """FINN_FALLBACK_MODEL may list several models, tried in order: 'gemini/x,groq/y'."""
    return [m.strip() for m in FALLBACK_MODEL.split(",") if m.strip()]


def available(tier: str = "fast") -> bool:
    """True when a key is configured for this tier's model or for a fallback model."""
    return _has_key(model_for(tier)) or any(_has_key(m) for m in _fallbacks())


def _retry_after(message: str) -> float:
    """Seconds the provider asks us to wait, read from its rate-limit message ('retry in 11h49m30.9s')."""
    match = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", message)
    if not match or not any(match.groups()):
        return 20.0
    hours, minutes, seconds = (float(g) if g else 0.0 for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def _parse_json(text: str):
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except ValueError:
        start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
        end = max(text.rfind("}"), text.rfind("]"))
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def choices() -> list[dict]:
    """Models the app may offer for research: the configured list, minus any without a key."""
    seen, out = set(), []
    for model in [model_for("fast"), *MODEL_CHOICES]:
        if model in seen or not _has_key(model):
            continue
        seen.add(model)
        provider = {"gemini": "Google", "anthropic": "Anthropic", "groq": "Groq",
                    "ollama": "Local"}.get(model.split("/")[0], model.split("/")[0])
        out.append({"id": model, "name": model.split("/")[-1], "provider": provider,
                    "default": model == model_for("fast")})
    return out


def ask(system: str, user: str, tier: str = "fast", as_json: bool = True, max_tokens: int = 4000,
        model: str | None = None, used: dict | None = None):
    """Call a model. Returns parsed JSON (default) or text. Raises if no key is set.

    `model` overrides the tier's model (the investor picked one in the app). `used` collects, per tier,
    the names of the models that actually answered, since a fallback may have stepped in."""
    model = model or model_for(tier)
    digest = hashlib.sha1(json.dumps([model, system, user, as_json, max_tokens]).encode()).hexdigest()
    path = CACHE / "llm" / f"{digest}.json"
    hit = store.read(path)
    if hit is not None:
        with _usage_lock:
            usage["cache_hits"] += 1
        return hit["value"]
    if not (_has_key(model) or any(_has_key(m) for m in _fallbacks())):
        raise RuntimeError(f"no API key configured for model '{model}'")

    import litellm  # imported lazily: it is slow to import and not needed for cached runs

    litellm.suppress_debug_info = True   # no "Give Feedback" banner on every failed call
    litellm.drop_params = True           # newer models reject some settings (e.g. temperature); drop, don't fail
    # Try the tier's model, then the fallback. A provider that is overloaded or timing out is not worth
    # waiting on, so those errors move straight to the next model; a rate limit gets one patient retry.
    candidates = [model] + [m for m in _fallbacks() if m != model and _has_key(m)]
    last_error, value, response, winner = None, None, None, None
    for candidate in candidates:
        if time.time() < _down_until.get(candidate, 0) and candidate != candidates[-1]:
            continue                           # failed moments ago: do not make every call wait on it again
        for attempt in range(3):
            try:
                response = litellm.completion(
                    model=candidate,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    temperature=0,
                    max_tokens=max_tokens,
                    timeout=75,
                    **({"response_format": {"type": "json_object"}} if as_json else {}),
                )
                text = response.choices[0].message.content or ""
                value = _parse_json(text) if as_json else text.strip()
                winner = candidate
                break
            except Exception as error:
                last_error = error
                message = str(error).lower()
                if "timeout" in message or "timed out" in message or "503" in message or "404" in message:
                    _down_until[candidate] = time.time() + 300
                    break                      # provider is down or the model is gone: next candidate
                if "429" in message or "rate" in message:
                    wait = _retry_after(message)
                    if wait > 40:              # a daily quota is gone: stop asking until it resets
                        _down_until[candidate] = time.time() + min(wait, 3600)
                        break
                    time.sleep(wait + 1)       # a per-minute limit: worth waiting to stay on the free model
        if winner:
            break
    if not winner:
        raise RuntimeError(f"model call failed ({' then '.join(candidates)}): {last_error}")
    model = winner
    used_models.setdefault(tier, set()).add(model.split("/")[-1])
    if used is not None:
        used.setdefault(tier, set()).add(model.split("/")[-1])

    tokens = getattr(response, "usage", None)
    with _usage_lock:
        usage["calls"] += 1
        bucket = usage["by_model"].setdefault(model, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        bucket["calls"] += 1
        if tokens:
            for field, attr in (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens")):
                count = getattr(tokens, attr, 0) or 0
                usage[field] += count
                bucket[field] += count
    store.write(path, {"model": model, "value": value})
    return value
