"""Pure logic for deciding how to update an existing forum post. No I/O.

Given the stored post state (pre-edit body hash, old link map) and the
freshly rendered replacement (new body + new link map), plus the live body
fetched from the forum, decide whether to:

- do nothing (NOOP — no URL changes and no reason to edit),
- replace the whole body (WHOLE_BODY),
- swap specific URLs in-place (SURGICAL — preserves user comments/edits),
- skip with a user-visible alert (SKIP_AND_ALERT — manual edits detected
  and policy says skip).

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §7.7.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class UpdateAction(str, Enum):
    NOOP = "noop"
    WHOLE_BODY = "whole_body"
    SURGICAL = "surgical"
    SKIP_AND_ALERT = "skip_and_alert"


@dataclass
class UpdatePlan:
    action: UpdateAction
    body_to_post: str = ""
    swapped_urls: dict[str, str] = field(default_factory=dict)
    reason: str = ""


def _build_swap_map(old: dict, new: dict) -> dict[str, str]:
    """Pair URLs by category + index. Best-effort when counts mismatch."""
    swap: dict[str, str] = {}
    for cat in ("image_hosts", "file_hosts", "others"):
        old_urls = [e["url"] for e in (old.get(cat) or []) if e.get("url")]
        new_urls = [e["url"] for e in (new.get(cat) or []) if e.get("url")]
        for o, n in zip(old_urls, new_urls):
            if o and n and o != n:
                swap[o] = n
    return swap


def _surgical_body(live_body: str, swap: dict[str, str]) -> str:
    body = live_body
    for old, new in swap.items():
        body = body.replace(old, new)
    return body


def plan_update(
    *,
    update_mode: str,
    manual_edit_handling: str,
    stored_body_hash: str,
    live_body: str,
    live_body_hash: str,
    old_link_map: dict,
    new_body: str,
    new_link_map: dict,
) -> UpdatePlan:
    """Decide how to update an existing post. Returns an :class:`UpdatePlan`.

    ``update_mode`` is one of ``"whole" | "surgical" | "whole_then_surgical"``.
    ``manual_edit_handling`` is one of
    ``"skip_alert" | "overwrite" | "surgical"``.
    """
    manual_edits_detected = bool(
        stored_body_hash and live_body_hash
        and stored_body_hash != live_body_hash
    )
    swap_map = _build_swap_map(old_link_map or {}, new_link_map or {})
    has_url_changes = bool(swap_map)

    # Surgical mode — always swap, never replace wholesale.
    if update_mode == "surgical":
        if not has_url_changes:
            return UpdatePlan(UpdateAction.NOOP, reason="no URL changes")
        reason = "surgical mode"
        if manual_edits_detected:
            reason += " (manual edits preserved)"
        return UpdatePlan(
            UpdateAction.SURGICAL,
            body_to_post=_surgical_body(live_body, swap_map),
            swapped_urls=swap_map,
            reason=reason,
        )

    # Whole or whole_then_surgical — no manual edits → replace whole.
    if not manual_edits_detected:
        return UpdatePlan(
            UpdateAction.WHOLE_BODY,
            body_to_post=new_body,
            reason="no manual edits",
        )

    # Manual edits detected: respect policy.
    if manual_edit_handling == "overwrite":
        return UpdatePlan(
            UpdateAction.WHOLE_BODY,
            body_to_post=new_body,
            reason="overwrite per setting",
        )

    if manual_edit_handling == "skip_alert":
        # whole_then_surgical overrides skip_alert when there are URL
        # changes worth swapping; otherwise skip and alert.
        if update_mode == "whole_then_surgical":
            if not has_url_changes:
                return UpdatePlan(
                    UpdateAction.SKIP_AND_ALERT,
                    reason="manual edits + no URL changes to swap",
                )
            return UpdatePlan(
                UpdateAction.SURGICAL,
                body_to_post=_surgical_body(live_body, swap_map),
                swapped_urls=swap_map,
                reason="manual edits \u2192 fall back to surgical",
            )
        return UpdatePlan(
            UpdateAction.SKIP_AND_ALERT,
            reason="manual edits detected, policy: skip and alert",
        )

    if manual_edit_handling == "surgical":
        if not has_url_changes:
            return UpdatePlan(
                UpdateAction.SKIP_AND_ALERT,
                reason="manual edits + no URL changes to swap",
            )
        return UpdatePlan(
            UpdateAction.SURGICAL,
            body_to_post=_surgical_body(live_body, swap_map),
            swapped_urls=swap_map,
            reason="surgical per manual_edit_handling",
        )

    return UpdatePlan(
        UpdateAction.SKIP_AND_ALERT,
        reason=f"unknown manual_edit_handling: {manual_edit_handling}",
    )
