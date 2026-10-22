from typing import Any

from app.supabase_rest import SupabaseRestError, privileged_request


async def notify_user(
    user_id: str,
    *,
    notification_type: str,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> bool:
    """Best-effort server notification delivery with database-level deduplication."""
    try:
        if dedupe_key:
            existing = await privileged_request(
                "GET",
                "notifications",
                params={"user_id": f"eq.{user_id}", "dedupe_key": f"eq.{dedupe_key}", "select": "id", "limit": "1"},
            )
            if existing:
                return False
        await privileged_request(
            "POST",
            "notifications",
            body={
                "user_id": user_id,
                "type": notification_type,
                "title": title,
                "body": body,
                "data": data or {},
                "dedupe_key": dedupe_key,
            },
            prefer="return=minimal",
        )
        return True
    except SupabaseRestError as error:
        # A concurrent request may win the unique dedupe key race. It is already delivered.
        if error.status_code == 409 and dedupe_key:
            return False
        return False


async def notify_admins(*, notification_type: str, title: str, body: str, data: dict[str, Any], dedupe_prefix: str) -> int:
    try:
        admins = await privileged_request("GET", "profiles", params={"role": "eq.admin", "select": "id"})
    except SupabaseRestError:
        return 0
    delivered = 0
    for admin in admins or []:
        if await notify_user(
            admin["id"],
            notification_type=notification_type,
            title=title,
            body=body,
            data=data,
            dedupe_key=f"{dedupe_prefix}:{admin['id']}",
        ):
            delivered += 1
    return delivered
