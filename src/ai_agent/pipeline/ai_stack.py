"""Production copy stack: fast stream + quality writer + parallel verifiers + hard ground.

Closed world: the hearing sheet is the only allowed knowledge.
All models are free (Z.AI Flash + NVIDIA NIM). DeepSeek is excluded for latency.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from ai_agent.models.registry import ModelRegistry
from ai_agent.models.types import ChatMessage
from ai_agent.pipeline.copy_generator import demo_messages, parse_copy_json
from ai_agent.pipeline.grounding import ground_copy
from ai_agent.pipeline.schema import normalize_copy, seal_structured_fields
from ai_agent.pipeline.validate import prepare_copy_for_wordpress
from ai_agent.pipeline.verify import apply_issues_audited, parse_issues, verifier_messages

# Fast first token for the UI.
STREAM_WRITERS = ["glm-4.5-flash", "glm-4.7-flash", "nvidia-minimax-m3"]
# Stronger Japanese draft; swapped in if it finishes in time.
QUALITY_WRITERS = ["nvidia-nemotron-super-49b", "glm-4.7-flash"]
# Independent families, compact issue JSON only.
VERIFIERS = [
    "glm-4.7-flash",
    "nvidia-nemotron-super-49b",
    "nvidia-kimi-k3",
]
FREE_WRITER_CANDIDATES = STREAM_WRITERS + QUALITY_WRITERS
MAX_VERIFIERS = 3
# Improve must polish the finished writer draft (sequential) — allow real model latency.
QUALITY_TIMEOUT_SEC = 90.0
# Explicit user-selected verifiers get a production SLA (not a demo sprint).
VERIFY_SLA_SEC = 35.0
WRITER_TEMPERATURE = 0.2
VERIFY_TEMPERATURE = 0.0
WRITER_MAX_TOKENS = 2800
VERIFY_MAX_TOKENS = 500

_failures: dict[str, int] = {}


@dataclass
class StackResult:
    copy: dict[str, Any]
    models_used: list[str]
    stream_writer: str
    quality_writer: str
    verifiers: list[str]
    issues_applied: int
    grounding_hits: int
    estimated_usd: float = 0.0
    architecture: dict[str, Any] = field(default_factory=dict)
    roles: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)


def gemini_reasoning_effort(model_id: str) -> str:
    """Lowest supported thinking level for Gemini OpenAI-compat calls.

    Prefer ``minimal`` for speed (3.5 Flash / Flash-Lite).
    Pro rejects ``minimal`` — only low|medium|high.
    """
    mid = (model_id or "").lower()
    if any(
        token in mid
        for token in (
            "gemini-3.1-pro",
            "gemini-3-pro",
            "gemini-3.6",
            "gemini-3.7",
            "gemini-3.8",
        )
    ):
        return "low"
    return "minimal"


def extra_body_for(model_id: str) -> dict[str, Any]:
    mid = (model_id or "").lower()
    # GLM-5.3 always thinks; disabling is rejected — use low effort for copy JSON.
    if mid == "glm-5.3":
        return {"reasoning_effort": "low"}
    if mid.startswith("glm-"):
        return {"thinking": {"type": "disabled"}}
    # Gemini OpenAI-compat (v1beta/openai): reasoning_effort is the supported
    # thinking control. Do not send Google-native generationConfig / thinkingConfig.
    if mid.startswith("gemini-") or "gemini" in mid:
        return {"reasoning_effort": gemini_reasoning_effort(mid)}
    return {}


def writer_max_tokens_for(model_id: str) -> int:
    mid = (model_id or "").lower()
    if mid.startswith("gemini-"):
        # Extra headroom if the model still spends a few thinking tokens.
        return max(WRITER_MAX_TOKENS, 4096)
    return WRITER_MAX_TOKENS


def _healthy(model_id: str) -> bool:
    return _failures.get(model_id, 0) < 2


def _mark_ok(model_id: str) -> None:
    _failures[model_id] = 0


def _mark_fail(model_id: str) -> None:
    _failures[model_id] = _failures.get(model_id, 0) + 1


def configured_ids(registry: ModelRegistry) -> dict[str, bool]:
    return {item["id"]: bool(item.get("key_configured")) for item in registry.available()}


def pick_models(registry: ModelRegistry, candidates: list[str], *, exclude: str = "") -> list[str]:
    available = configured_ids(registry)
    out: list[str] = []
    for model in candidates:
        if model == exclude:
            continue
        if available.get(model) and _healthy(model) and model not in out:
            out.append(model)
    return out


def _chat_copy(
    registry: ModelRegistry,
    model: str,
    messages: list[ChatMessage],
    *,
    max_tokens: int,
    hearing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = registry.chat(
        model,
        messages,
        temperature=WRITER_TEMPERATURE,
        max_tokens=max_tokens,
        extra_body=extra_body_for(model),
    )
    # Non-stream path includes usage + estimated_usd, which we want for cost display.
    return parse_copy_json(result.content, hearing=hearing), float(result.estimated_usd or 0.0)


def _polish_copy(
    registry: ModelRegistry,
    model: str,
    hearing: dict[str, Any],
    draft: dict[str, Any],
    *,
    max_tokens: int,
) -> tuple[dict[str, Any], float]:
    """Improve model polishes the Writer draft (same keys, hearing-only facts)."""
    draft_json = json.dumps(draft, ensure_ascii=False, indent=2)
    facts = json.dumps(hearing, ensure_ascii=False)
    messages = [
        ChatMessage(
            role="system",
            content=(
                "あなたは日本語Web原稿の品質向上担当です。"
                "入力のJSON原稿を、より自然で信頼できる日本語に磨いてください。"
                "キーは維持: title, slug, heading, lead, body_paragraphs, cta, notes。"
                "body_paragraphsは配列のまま。ヒアリングに無い事実・料金・駅・電話・個室・香り・効果効能は追加しない。"
                "コードフェンス禁止。JSONオブジェクトのみ返す。"
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                "次の原稿JSONを磨いてください。許可された事実以外は使わないでください。\n"
                f"許可された事実:\n{facts}\n\n原稿JSON:\n{draft_json}"
            ),
        ),
    ]
    return _chat_copy(registry, model, messages, max_tokens=max_tokens, hearing=hearing)


def _chat_issues(
    registry: ModelRegistry, model: str, hearing: dict[str, Any], draft: dict[str, Any]
) -> tuple[list[dict[str, str]], float]:
    """Non-stream fallback when a verifier stream returns empty."""
    result = registry.chat(
        model,
        verifier_messages(hearing, draft),
        temperature=VERIFY_TEMPERATURE,
        max_tokens=VERIFY_MAX_TOKENS,
        extra_body=extra_body_for(model),
    )
    return parse_issues(result.content), float(result.estimated_usd or 0.0)


# Typical compact verifier JSON ({"issues":[...]}) — used only to scale real streamed chars.
VERIFY_CHAR_TARGET = 280


def _verify_live_pct(
    *,
    has_improve: bool,
    streamed_chars: int,
    done_count: int,
    total: int,
) -> int:
    """Map real verifier output + completions into pipeline % (no wall-clock invent)."""
    base = _pipeline_progress("verify", has_improve=has_improve, has_verify=True)
    ground = _pipeline_progress("ground", has_improve=has_improve, has_verify=True)
    span = max(8, ground - base - 2)
    if streamed_chars <= 0 and done_count <= 0:
        return base
    char_p = min(0.88, streamed_chars / float(VERIFY_CHAR_TARGET)) if streamed_chars else 0.0
    done_p = (done_count / float(total)) if total else 0.0
    # Prefer real tokens; completions still count when JSON is tiny.
    within = max(char_p, done_p * 0.95)
    within = min(0.90, within)
    return min(base + int(within * span), ground - 2)


def _count_grounding(before: dict[str, Any], after: dict[str, Any]) -> int:
    before_n = json.dumps(before, ensure_ascii=False).count("要ヒアリング")
    after_n = json.dumps(after, ensure_ascii=False).count("要ヒアリング")
    return max(0, after_n - before_n)


def _pipeline_progress(
    stage_id: str,
    *,
    has_improve: bool,
    has_verify: bool,
) -> int:
    """Deterministic % for UI progress bars (production pipeline stages)."""
    if has_improve and has_verify:
        table = {
            "write": 8,
            "improve": 42,
            "quality_swap": 58,
            "verify": 75,
            "ground": 94,
        }
    elif has_verify:
        table = {"write": 12, "verify": 68, "ground": 94}
    elif has_improve:
        table = {"write": 12, "improve": 55, "quality_swap": 72, "ground": 94}
    else:
        table = {"write": 20, "ground": 90}
    return int(table.get(stage_id, 0))


def _stage_payload(
    stage_id: str,
    *,
    has_improve: bool,
    has_verify: bool,
    **extra: Any,
) -> dict[str, Any]:
    out = {"id": stage_id, **extra}
    out["progress"] = _pipeline_progress(
        stage_id, has_improve=has_improve, has_verify=has_verify
    )
    return out


async def run_copy_stack(
    registry: ModelRegistry,
    hearing: dict[str, Any],
) -> AsyncIterator[tuple[str, Any]]:
    """Yields ('token'|'stage'|'done', payload). Final payload is StackResult."""
    stream_candidates = pick_models(registry, STREAM_WRITERS)
    if not stream_candidates:
        raise RuntimeError("No available free writer")
    stream_model = stream_candidates[0]
    quality_candidates = pick_models(registry, QUALITY_WRITERS, exclude=stream_model)
    quality_model = quality_candidates[0] if quality_candidates else ""
    async for item in run_writer_production(
        registry,
        hearing,
        writer=stream_model,
        quality_writer=quality_model,
    ):
        yield item


async def run_writer_production(
    registry: ModelRegistry,
    hearing: dict[str, Any],
    *,
    writer: str,
    quality_writer: str = "",
    messages: list[ChatMessage] | None = None,
    verifier_pool: list[str] | None = None,
) -> AsyncIterator[tuple[str, Any]]:
    """Full industry stack: Writer stream → Improve polish → parallel verify → ground → seal."""
    page = hearing.get("target_page") or "top"
    write_messages = messages or demo_messages(hearing, page=page)
    stream_model = writer
    quality_model = quality_writer if quality_writer and quality_writer != writer else ""

    total_cost_usd = 0.0
    improve_status = "skipped"
    verifier_statuses: list[dict[str, str]] = []
    has_improve = bool(quality_model)
    has_verify = bool(verifier_pool)  # explicit plan; refined later if empty after pick

    yield (
        "stage",
        _stage_payload(
            "write",
            has_improve=has_improve,
            has_verify=True if verifier_pool is None else bool(verifier_pool),
            writer=stream_model,
            quality_writer=quality_model,
        ),
    )
    chunks: list[str] = []
    write_max = writer_max_tokens_for(stream_model)
    write_extra = extra_body_for(stream_model)
    write_started = time.perf_counter()
    streamed_chars = 0
    has_verify_plan = True if verifier_pool is None else bool(verifier_pool)

    def _write_progress_event() -> dict[str, Any]:
        """Honest write progress: % only moves with real streamed chars (no TTFB fake climb)."""
        elapsed = time.perf_counter() - write_started
        base = _pipeline_progress(
            "write", has_improve=has_improve, has_verify=has_verify_plan
        )
        if streamed_chars <= 0:
            # Heartbeat only — elapsed in the label; % stays at stage base until first token.
            return {
                "stage": "write",
                "progress": base,
                "chars": 0,
                "elapsed_ms": int(elapsed * 1000),
                "waiting_first_token": True,
                "label": f"Writer waiting for first tokens · {int(elapsed)}s",
            }
        # Real output only: map chars → within-stage fill (no wall-clock invent).
        char_p = min(0.88, streamed_chars / 1800.0)
        span = 35 if has_improve else 50
        live_pct = min(base + int(char_p * span), 55 if has_improve else 70)
        return {
            "stage": "write",
            "progress": live_pct,
            "chars": streamed_chars,
            "elapsed_ms": int(elapsed * 1000),
            "waiting_first_token": False,
            "label": f"Writer drafting · {streamed_chars} chars",
        }

    # Stream tokens on a task so we can heartbeat during long TTFB silence.
    token_q: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    async def _produce_write_tokens() -> None:
        try:
            async for token in registry.chat_stream(
                stream_model,
                write_messages,
                temperature=WRITER_TEMPERATURE,
                max_tokens=write_max,
                extra_body=write_extra,
            ):
                await token_q.put(("token", token))
            await token_q.put(("done", None))
        except Exception as exc:  # noqa: BLE001 — forwarded to consumer
            await token_q.put(("error", exc))

    produce_task = asyncio.create_task(_produce_write_tokens())
    stream_err: Exception | None = None
    try:
        while True:
            try:
                kind, payload = await asyncio.wait_for(token_q.get(), timeout=1.5)
            except asyncio.TimeoutError:
                yield ("progress", _write_progress_event())
                continue
            if kind == "error":
                stream_err = payload if isinstance(payload, Exception) else RuntimeError(str(payload))
                break
            if kind == "done":
                break
            token = str(payload or "")
            chunks.append(token)
            streamed_chars += len(token)
            yield ("token", token)
            yield ("progress", _write_progress_event())
        await produce_task
    except Exception as exc:
        stream_err = exc
        produce_task.cancel()
        try:
            await produce_task
        except Exception:
            pass

    write_ms = int((time.perf_counter() - write_started) * 1000)
    try:
        if stream_err and not "".join(chunks).strip():
            raise stream_err
        joined = "".join(chunks).strip()
        if not joined:
            # Gemini thinking models can stream empty content; fall back to non-stream.
            result = await asyncio.to_thread(
                registry.chat,
                stream_model,
                write_messages,
                temperature=WRITER_TEMPERATURE,
                max_tokens=write_max,
                extra_body=write_extra,
            )
            joined = (result.content or "").strip()
            if joined:
                yield ("token", joined)
        if not joined:
            raise RuntimeError(
                f"{stream_model} returned empty content (thinking may have used the budget). "
                "Retry or pick gemini-3.5-flash-lite."
            )
        stream_copy = parse_copy_json(joined, hearing=hearing)
        _mark_ok(stream_model)
    except Exception as write_exc:
        _mark_fail(stream_model)
        mid = (stream_model or "").lower()
        # Free Z.AI Flash is often overloaded (HTTP 429 / code 1305) — fall back once.
        if mid == "glm-4.7-flash":
            fallback = "glm-4.5-flash"
            try:
                result = await asyncio.to_thread(
                    registry.chat,
                    fallback,
                    write_messages,
                    temperature=WRITER_TEMPERATURE,
                    max_tokens=writer_max_tokens_for(fallback),
                    extra_body=extra_body_for(fallback),
                )
                stream_copy = parse_copy_json(result.content or "", hearing=hearing)
                stream_model = fallback
                _mark_ok(fallback)
                yield (
                    "stage",
                    _stage_payload(
                        "write",
                        has_improve=has_improve,
                        has_verify=bool(verifier_pool),
                        writer=fallback,
                        quality_writer=quality_model,
                        fallback_from="glm-4.7-flash",
                    ),
                )
                if result.content:
                    yield ("token", result.content)
            except Exception:
                raise write_exc from None
        # One non-stream retry for Gemini (thinking/truncation).
        elif mid.startswith("gemini-"):
            try:
                result = await asyncio.to_thread(
                    registry.chat,
                    stream_model,
                    write_messages,
                    temperature=WRITER_TEMPERATURE,
                    max_tokens=write_max,
                    extra_body=write_extra,
                )
                stream_copy = parse_copy_json(result.content or "", hearing=hearing)
                _mark_ok(stream_model)
            except Exception:
                raise write_exc from None
        # MiniMax often streams almost-valid JSON (forgot ] on body_paragraphs); retry once.
        elif "minimax" in mid:
            try:
                result = await asyncio.to_thread(
                    registry.chat,
                    stream_model,
                    write_messages,
                    temperature=0.1,
                    max_tokens=write_max,
                    extra_body=write_extra,
                )
                stream_copy = parse_copy_json(result.content or "", hearing=hearing)
                _mark_ok(stream_model)
                if result.content:
                    yield ("token", result.content)
            except Exception:
                raise write_exc from None
        else:
            raise

    draft = stream_copy
    stream_writer_used = stream_model
    quality_used = ""
    improve_ms = 0
    verify_ms = 0

    # Improve: sequential polish of the Writer draft (not a parallel race).
    if quality_model:
        yield (
            "stage",
            _stage_payload(
                "improve",
                has_improve=True,
                has_verify=bool(verifier_pool),
                writer=stream_writer_used,
                quality_writer=quality_model,
            ),
        )
        improve_started = time.perf_counter()
        polish_task = asyncio.create_task(
            asyncio.to_thread(
                _polish_copy,
                registry,
                quality_model,
                hearing,
                draft,
                max_tokens=writer_max_tokens_for(quality_model),
            )
        )
        try:
            while True:
                if time.perf_counter() - improve_started >= QUALITY_TIMEOUT_SEC:
                    raise asyncio.TimeoutError()
                done, _pending = await asyncio.wait({polish_task}, timeout=1.5)
                if polish_task in done:
                    break
                elapsed = time.perf_counter() - improve_started
                # Heartbeat only — % frozen at Improve stage base until polish returns.
                yield (
                    "progress",
                    {
                        "stage": "improve",
                        "progress": _pipeline_progress(
                            "improve", has_improve=True, has_verify=bool(verifier_pool)
                        ),
                        "elapsed_ms": int(elapsed * 1000),
                        "label": f"Improve polishing · {int(elapsed)}s",
                    },
                )
            polished, polish_cost = await polish_task
            draft = polished
            quality_used = quality_model
            improve_status = "ok"
            total_cost_usd += polish_cost
            _mark_ok(quality_model)
            improve_ms = int((time.perf_counter() - improve_started) * 1000)
            yield (
                "stage",
                _stage_payload(
                    "quality_swap",
                    has_improve=True,
                    has_verify=bool(verifier_pool),
                    writer=stream_writer_used,
                    quality_writer=quality_used,
                    duration_ms=improve_ms,
                ),
            )
        except asyncio.TimeoutError:
            polish_task.cancel()
            improve_status = "timeout"
            improve_ms = int((time.perf_counter() - improve_started) * 1000)
            _mark_fail(quality_model)
        except Exception:
            polish_task.cancel()
            improve_status = "error"
            improve_ms = int((time.perf_counter() - improve_started) * 1000)
            _mark_fail(quality_model)

    draft = seal_structured_fields(normalize_copy(draft), hearing)

    pool = VERIFIERS if verifier_pool is None else list(verifier_pool)
    # Allow self-verify when client selected one model (writer == verifier).
    allow_self = len(pool) == 1 and pool[0] == stream_writer_used
    # Gemini Flash self-verify often over-replaces prose with 「要ヒアリング」 and ruins copy.
    # Record skipped so UI never looks like a fake successful verify.
    if allow_self and (stream_writer_used or "").startswith("gemini-"):
        allow_self = False
        pool = []
        verifier_statuses.append(
            {
                "model": stream_writer_used,
                "status": "skipped",
                "duration_ms": 0,
                "reason": "gemini_self_verify_disabled",
            }
        )
    # Prefer excluding the Improve model from verify when both ran; else exclude Writer.
    exclude = ""
    if not allow_self:
        exclude = quality_used or stream_writer_used
    verifier_models = pick_models(registry, pool, exclude=exclude)[:MAX_VERIFIERS]
    # Auto-pick default verifiers only when caller did not pass an explicit pool.
    if verifier_pool is None and len(verifier_models) < 1:
        verifier_models = pick_models(registry, VERIFIERS + STREAM_WRITERS, exclude=exclude)[
            :MAX_VERIFIERS
        ]

    # Keep planned verifiers even if temporarily marked unhealthy (user explicit pick).
    if verifier_pool is not None:
        planned = [m for m in pool if m != exclude][:MAX_VERIFIERS]
        for mid in planned:
            if mid not in verifier_models and configured_ids(registry).get(mid):
                verifier_models.append(mid)
        verifier_models = verifier_models[:MAX_VERIFIERS]

    has_verify = bool(verifier_models)
    # Skip the verify stage entirely when none are planned (e.g. single-model draft).
    if has_verify:
        yield (
            "stage",
            _stage_payload(
                "verify",
                has_improve=has_improve,
                has_verify=True,
                writer=stream_writer_used,
                quality_writer=quality_used,
                verifiers=verifier_models,
            ),
        )

    issues: list[dict[str, str]] = []
    verifiers_ok: list[str] = []
    verify_started = time.perf_counter()
    if verifier_models:
        total_v = len(verifier_models)
        verify_chars = 0
        done_count = 0
        event_q: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

        async def _produce_verifier(model: str) -> None:
            started = time.perf_counter()
            chunks: list[str] = []
            try:
                async for token in registry.chat_stream(
                    model,
                    verifier_messages(hearing, draft),
                    temperature=VERIFY_TEMPERATURE,
                    max_tokens=VERIFY_MAX_TOKENS,
                    extra_body=extra_body_for(model),
                ):
                    text = str(token or "")
                    if not text:
                        continue
                    chunks.append(text)
                    await event_q.put(("chunk", model, len(text)))
                content = "".join(chunks).strip()
                cost = 0.0
                if not content:
                    # Stream empty (thinking models) — one non-stream retry.
                    found, cost = await asyncio.to_thread(
                        _chat_issues, registry, model, hearing, draft
                    )
                else:
                    found = parse_issues(content)
                await event_q.put(
                    (
                        "done",
                        {
                            "model": model,
                            "issues": found,
                            "cost": cost,
                            "duration_ms": int((time.perf_counter() - started) * 1000),
                            "chars": len(content),
                        },
                    )
                )
            except Exception as exc:  # noqa: BLE001 — surfaced as verifier error
                await event_q.put(
                    (
                        "error",
                        {
                            "model": model,
                            "error": exc,
                            "duration_ms": int((time.perf_counter() - started) * 1000),
                        },
                    )
                )

        producers = [asyncio.create_task(_produce_verifier(m)) for m in verifier_models]
        finished = 0
        while finished < total_v:
            elapsed = time.perf_counter() - verify_started
            if elapsed >= VERIFY_SLA_SEC:
                for task in producers:
                    if not task.done():
                        task.cancel()
                # Mark any model not yet recorded as timeout.
                recorded = {v.get("model") for v in verifier_statuses}
                for model in verifier_models:
                    if model not in recorded:
                        verifier_statuses.append(
                            {
                                "model": model,
                                "status": "timeout",
                                "duration_ms": int(elapsed * 1000),
                            }
                        )
                        _mark_fail(model)
                break
            try:
                item = await asyncio.wait_for(event_q.get(), timeout=1.5)
            except asyncio.TimeoutError:
                # Heartbeat: freeze % until first real verifier char; then char-based.
                yield (
                    "progress",
                    {
                        "stage": "verify",
                        "progress": _verify_live_pct(
                            has_improve=has_improve,
                            streamed_chars=verify_chars,
                            done_count=done_count,
                            total=total_v,
                        ),
                        "chars": verify_chars,
                        "elapsed_ms": int(elapsed * 1000),
                        "waiting_first_token": verify_chars <= 0,
                        "verifiers_done": done_count,
                        "verifiers_total": total_v,
                        "label": (
                            f"Verifier drafting · {verify_chars} chars"
                            f" · {done_count}/{total_v} done"
                            if verify_chars
                            else f"Verifier waiting for first tokens · {int(elapsed)}s"
                        ),
                    },
                )
                continue
            kind = item[0]
            if kind == "chunk":
                n = int(item[2])
                verify_chars += n
                yield (
                    "progress",
                    {
                        "stage": "verify",
                        "progress": _verify_live_pct(
                            has_improve=has_improve,
                            streamed_chars=verify_chars,
                            done_count=done_count,
                            total=total_v,
                        ),
                        "chars": verify_chars,
                        "elapsed_ms": int((time.perf_counter() - verify_started) * 1000),
                        "waiting_first_token": False,
                        "verifiers_done": done_count,
                        "verifiers_total": total_v,
                        "label": (
                            f"Verifier drafting · {verify_chars} chars"
                            f" · {done_count}/{total_v} done"
                        ),
                    },
                )
            elif kind == "done":
                finished += 1
                done_count += 1
                payload = item[1]
                model = payload["model"]
                found = payload["issues"]
                _mark_ok(model)
                verifiers_ok.append(model)
                verifier_statuses.append(
                    {
                        "model": model,
                        "status": "ok",
                        "duration_ms": int(payload["duration_ms"]),
                    }
                )
                issues.extend(found)
                total_cost_usd += float(payload.get("cost") or 0.0)
                # If fallback filled content without stream chunks, count those chars once.
                fb_chars = int(payload.get("chars") or 0)
                if fb_chars and verify_chars < fb_chars:
                    verify_chars = fb_chars
                yield (
                    "progress",
                    {
                        "stage": "verify",
                        "progress": _verify_live_pct(
                            has_improve=has_improve,
                            streamed_chars=verify_chars,
                            done_count=done_count,
                            total=total_v,
                        ),
                        "chars": verify_chars,
                        "elapsed_ms": int((time.perf_counter() - verify_started) * 1000),
                        "waiting_first_token": False,
                        "verifiers_done": done_count,
                        "verifiers_total": total_v,
                        "label": (
                            f"Verifier {done_count}/{total_v} complete"
                            f" · {verify_chars} chars"
                        ),
                    },
                )
            elif kind == "error":
                finished += 1
                payload = item[1]
                model = payload["model"]
                _mark_fail(model)
                verifier_statuses.append(
                    {
                        "model": model,
                        "status": "error",
                        "duration_ms": int(payload["duration_ms"]),
                    }
                )
        for task in producers:
            if not task.done():
                task.cancel()
            try:
                await task
            except Exception:
                pass
    elif verifier_pool:
        for mid in verifier_pool[:MAX_VERIFIERS]:
            verifier_statuses.append(
                {"model": mid, "status": "skipped", "duration_ms": 0}
            )
    verify_ms = int((time.perf_counter() - verify_started) * 1000)

    yield (
        "stage",
        _stage_payload(
            "ground",
            has_improve=has_improve,
            has_verify=has_verify,
            writer=stream_writer_used,
            quality_writer=quality_used,
            verifiers=verifiers_ok,
        ),
    )
    patched, issues_applied, _repair_log = apply_issues_audited(draft, issues, hearing)
    grounded = ground_copy(patched, hearing)
    sealed = seal_structured_fields(grounded, hearing)
    sealed, validation = prepare_copy_for_wordpress(sealed, hearing)
    grounding_hits = _count_grounding(draft, sealed) + issues_applied

    models_used = [stream_writer_used]
    if quality_used:
        models_used.append(quality_used)
    for mid in verifiers_ok:
        if mid not in models_used:
            models_used.append(mid)

    roles: dict[str, Any] = {
        "writer": {
            "model": stream_writer_used,
            "status": "ok",
            "duration_ms": write_ms,
        },
        "verifiers": list(verifier_statuses),
    }
    if quality_model:
        roles["improve"] = {
            "model": quality_model,
            "status": improve_status,
            "duration_ms": improve_ms,
        }

    yield (
        "done",
        StackResult(
            copy=sealed,
            models_used=models_used,
            stream_writer=stream_writer_used,
            quality_writer=quality_used,
            verifiers=verifiers_ok,
            issues_applied=issues_applied,
            grounding_hits=grounding_hits,
            estimated_usd=round(total_cost_usd, 6),
            roles=roles,
            validation=validation,
            architecture={
                "pattern": "production: writer → improve polish → parallel verify → deterministic ground + seal + validate",
                "knowledge": "hearing_sheet_only",
                "grade": "wordpress_draft_ready",
                "cost_usd": round(total_cost_usd, 6),
                "stream_writer": stream_writer_used,
                "quality_writer": quality_used,
                "verifiers": verifiers_ok,
                "roles": roles,
                "issues_applied": issues_applied,
                "grounding_hits": grounding_hits,
                "validation": validation,
                "sla_improve_sec": QUALITY_TIMEOUT_SEC,
                "sla_verify_sec": VERIFY_SLA_SEC,
            },
        ),
    )
