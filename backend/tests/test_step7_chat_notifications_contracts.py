import asyncio

from app.api import SupportConversationCreate, SupportHandoffRequest, SupportMessageCreate
from app.notifications import notify_user


def test_step7_payload_validation() -> None:
    assert SupportConversationCreate(subject="Delivery question").priority == "normal"
    assert SupportMessageCreate(content="Please help").content == "Please help"
    assert SupportHandoffRequest(reason="Need a human").context == {}


def test_step7_payload_limits_are_enforced() -> None:
    for constructor, kwargs in (
        (SupportConversationCreate, {"subject": "x"}),
        (SupportMessageCreate, {"content": ""}),
        (SupportHandoffRequest, {"reason": "x"}),
    ):
        try:
            constructor(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{constructor.__name__} accepted invalid input")


def test_notification_delivery_degrades_without_service_role(monkeypatch) -> None:
    async def fail(*args, **kwargs):
        from app.supabase_rest import SupabaseRestError

        raise SupabaseRestError(503, "service role unavailable")

    monkeypatch.setattr("app.notifications.privileged_request", fail)
    assert asyncio.run(notify_user("00000000-0000-0000-0000-000000000001", notification_type="test", title="t", body="b")) is False
