from datetime import datetime, timezone
import json
import re
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from app.supabase_rest import AuthContext, SupabaseRestError, authenticate, privileged_request, privileged_rpc_request, rest_request, rpc_request, storage_delete, storage_signed_url, storage_upload
from app.settings import settings
from app.ai_assistant import extract_search_intent, filter_catalog, grounded_assistant_reply, outfit_recommendations
from app.payment_providers import JazzCashAdapter, EasypaisaAdapter, PaymentProviderUnavailable, canonical_payload, ensure_provider_configured, verify_callback
from app.rate_limit import enforce_rate_limit
from app.notifications import notify_admins, notify_user
from app.n8n_webhooks import deliver_customer_registered, deliver_new_order
from app.tryon_images import ImageValidationError, MAX_IMAGE_BYTES, extension_for_mime, validate_image

router = APIRouter(prefix="/api/v1")

_AI_CATALOG_SELECT = "id,name,slug,description,category_id,price_pkr,active,categories(name,slug),product_images(*),product_variants(*,inventory(quantity,reserved_quantity))"


async def _ai_catalog(user: AuthContext | None, *, include_inventory: bool = False) -> list[dict]:
    """Read the public catalog; use the server-only key for stock aggregates when configured."""
    params = {"active": "eq.true", "select": _AI_CATALOG_SELECT, "order": "created_at.desc", "limit": "100"}
    if include_inventory and settings.supabase_service_role_key:
        return await privileged_request("GET", "products", params=params)
    return await rest_request("GET", "products", user.access_token if user else "", params=params)


async def current_user(authorization: Annotated[str | None, Header()] = None) -> AuthContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer session required")
    try:
        return await authenticate(authorization.split(" ", 1)[1])
    except SupabaseRestError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error


async def optional_current_user(authorization: Annotated[str | None, Header()] = None) -> AuthContext | None:
    if not authorization:
        return None
    return await current_user(authorization)


def require_role(*roles: str):
    async def dependency(user: Annotated[AuthContext, Depends(current_user)]) -> AuthContext:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return dependency


class SellerApplicationCreate(BaseModel):
    business_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=32)
    description: str | None = Field(default=None, max_length=2000)


class CustomerRegistered(BaseModel):
    full_name: str | None = Field(default=None, max_length=160)


@router.post("/auth/customer-registered", status_code=202)
async def customer_registered(
    payload: CustomerRegistered,
    user: Annotated[AuthContext, Depends(current_user)],
):
    """Queue a verified signup event for the configured n8n registration workflow."""
    delivered = await deliver_customer_registered(user.user_id, user.email, payload.full_name)
    return {"accepted": delivered, "event_type": "customer.registered"}


class SellerApplicationDecision(BaseModel):
    status: str = Field(pattern="^(approved|rejected)$")
    rejection_reason: str | None = Field(default=None, max_length=1000)


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=180)
    description: str | None = Field(default=None, max_length=5000)
    category_id: str | None = None
    price_pkr: int = Field(ge=0)
    seller_id: str | None = None


class ProductUpdate(ProductCreate):
    active: bool = True


class VariantCreate(BaseModel):
    sku: str = Field(min_length=2, max_length=80)
    size: str = Field(min_length=1, max_length=32)
    color: str = Field(min_length=1, max_length=64)
    price_pkr: int | None = Field(default=None, ge=0)
    quantity: int = Field(default=0, ge=0)


class InventoryAdjustment(BaseModel):
    quantity_delta: int
    reason: str = Field(min_length=2, max_length=160)


class WithdrawalCreate(BaseModel):
    amount_pkr: int = Field(gt=0)
    payout_method: str = Field(min_length=2, max_length=80)
    payout_reference: str | None = Field(default=None, max_length=180)
    idempotency_key: str = Field(min_length=8, max_length=120)


class CartItemCreate(BaseModel):
    variant_id: str
    quantity: int = Field(gt=0, le=100)


class CheckoutItem(BaseModel):
    variant_id: str
    quantity: int = Field(gt=0, le=100)


class CheckoutCreate(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=120)
    address_id: str
    items: list[CheckoutItem] = Field(min_length=1, max_length=100)
    delivery_pkr: int = Field(default=0, ge=0)
    discount_pkr: int = Field(default=0, ge=0)


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=32)


class CustomSizeCreate(BaseModel):
    name: str = Field(default="Custom measurements", min_length=2, max_length=80)
    unit: str = Field(default="cm", pattern="^(cm|in)$")
    chest: float | None = Field(default=None, gt=0, le=500)
    waist: float | None = Field(default=None, gt=0, le=500)
    shoulder: float | None = Field(default=None, gt=0, le=200)
    sleeve_length: float | None = Field(default=None, gt=0, le=300)
    shirt_length: float | None = Field(default=None, gt=0, le=300)
    inseam: float | None = Field(default=None, gt=0, le=300)


class AssistantRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    conversation_id: str | None = None


class TryOnJobCreate(BaseModel):
    upload_id: str
    product_id: str
    garment_category: str = Field(default="upper_body", min_length=2, max_length=40)


class ReviewCreate(BaseModel):
    product_id: str
    order_id: str | None = None
    rating: int = Field(ge=1, le=5)
    title: str | None = Field(default=None, max_length=160)
    body: str | None = Field(default=None, max_length=2000)


class SupportConversationCreate(BaseModel):
    subject: str = Field(min_length=2, max_length=200)
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")


class SupportMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class SupportHandoffRequest(BaseModel):
    reason: str = Field(default="Customer requested human support", min_length=2, max_length=1000)
    context: dict = Field(default_factory=dict)


class SupportConversationUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|pending|resolved|closed)$")
    priority: str | None = Field(default=None, pattern="^(low|normal|high|urgent)$")
    assigned_to: str | None = None


class DiscountCreate(BaseModel):
    code: str = Field(min_length=3, max_length=40, pattern=r"^[A-Z0-9_-]+$")
    kind: str = Field(pattern="^(percentage|fixed)$")
    value_pkr: int = Field(ge=0)
    min_subtotal_pkr: int = Field(default=0, ge=0)
    max_uses: int | None = Field(default=None, gt=0)
    ends_at: str | None = None


class PaymentInitiate(BaseModel):
    order_id: str
    provider: str = Field(pattern="^(jazzcash|easypaisa)$")
    idempotency_key: str = Field(default="", max_length=120)


class PaymentCallback(BaseModel):
    payment_id: str
    provider_event_id: str = Field(min_length=3, max_length=200)
    event_type: str = Field(min_length=2, max_length=80)
    status: str = Field(default="pending", pattern="^(pending|paid|failed|refunded)$")
    provider_reference: str | None = Field(default=None, max_length=200)
    payload: dict = Field(default_factory=dict)
    signature: str = Field(default="", max_length=256)


class RefundCreate(BaseModel):
    amount_pkr: int = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=120)
    reason: str | None = Field(default=None, max_length=500)


class WithdrawalDecision(BaseModel):
    status: str = Field(pattern="^(approved|rejected|paid|failed)$")
    payout_reference: str | None = Field(default=None, min_length=3, max_length=180)


class AdminOrderStatus(BaseModel):
    status: str = Field(pattern="^(pending|confirmed|packed|shipped|delivered|cancelled)$")


@router.post("/seller-applications", status_code=201)
async def apply_as_seller(payload: SellerApplicationCreate, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        rows = await rest_request("POST", "seller_applications", _token_placeholder(user), body={"user_id": user.user_id, **payload.model_dump()}, prefer="return=representation")
        return rows[0] if rows else None
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/me")
async def get_profile(user: Annotated[AuthContext, Depends(current_user)]):
    try:
        rows = await rest_request("GET", "profiles", _token_placeholder(user), params={"id": f"eq.{user.user_id}", "select": "id,full_name,phone,role,created_at,updated_at", "limit": "1"})
        return rows[0] if rows else {"id": user.user_id, "role": user.role}
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.patch("/me")
async def update_profile(payload: ProfileUpdate, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        rows = await rest_request("PATCH", "profiles", _token_placeholder(user), params={"id": f"eq.{user.user_id}"}, body=payload.model_dump(exclude_unset=True), prefer="return=representation")
        return rows[0] if rows else None
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/me/custom-sizes", status_code=201)
async def create_custom_size(payload: CustomSizeCreate, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        rows = await rest_request("POST", "custom_sizes", _token_placeholder(user), body={"user_id": user.user_id, **payload.model_dump()}, prefer="return=representation")
        return rows[0] if rows else None
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/me/custom-sizes")
async def list_custom_sizes(user: Annotated[AuthContext, Depends(current_user)]):
    try:
        return await rest_request("GET", "custom_sizes", _token_placeholder(user), params={"user_id": f"eq.{user.user_id}", "order": "created_at.desc"})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/wishlist")
async def get_wishlist(user: Annotated[AuthContext, Depends(current_user)]):
    try:
        return await rest_request("GET", "wishlists", user.access_token, params={"user_id": f"eq.{user.user_id}", "select": "product_id,created_at,products(id,name,slug,price_pkr,active)", "order": "created_at.desc"})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/wishlist/{product_id}", status_code=201)
async def add_wishlist(product_id: str, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        rows = await rest_request("POST", "wishlists", user.access_token, body={"user_id": user.user_id, "product_id": product_id}, prefer="return=representation,resolution=ignore-duplicates")
        return rows[0] if rows else {"product_id": product_id}
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.delete("/wishlist/{product_id}", status_code=204)
async def remove_wishlist(product_id: str, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        await rest_request("DELETE", "wishlists", user.access_token, params={"user_id": f"eq.{user.user_id}", "product_id": f"eq.{product_id}"})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/products/{product_id}/reviews")
async def product_reviews(product_id: str):
    try:
        return await rest_request("GET", "reviews", "", params={"product_id": f"eq.{product_id}", "approved": "eq.true", "order": "created_at.desc"})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/reviews", status_code=201)
async def create_review(payload: ReviewCreate, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        rows = await rest_request("POST", "reviews", user.access_token, body={"user_id": user.user_id, **payload.model_dump()}, prefer="return=representation")
        return rows[0] if rows else None
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/support/conversations", status_code=201)
async def create_support_conversation(payload: SupportConversationCreate, user: Annotated[AuthContext, Depends(current_user)]):
    enforce_rate_limit(f"support-create:{user.user_id}", limit=10, window_seconds=3600)
    try:
        ticket = await rest_request("POST", "support_tickets", user.access_token, body={"user_id": user.user_id, "subject": payload.subject, "priority": payload.priority}, prefer="return=representation")
        ticket_id = ticket[0]["id"]
        rows = await rest_request("POST", "conversations", user.access_token, body={"user_id": user.user_id, "support_ticket_id": ticket_id}, prefer="return=representation")
        await notify_admins(
            notification_type="support.new_ticket",
            title="New support request",
            body=payload.subject,
            data={"conversation_id": rows[0]["id"], "ticket_id": ticket_id},
            dedupe_prefix=f"support-ticket:{ticket_id}",
        )
        return rows[0] if rows else None
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/admin/support/conversations")
@router.get("/support/conversations")
async def list_support_conversations(user: Annotated[AuthContext, Depends(current_user)]):
    try:
        params = {"select": "*,messages(*),support_tickets(*)", "order": "created_at.desc"}
        if user.role != "admin":
            params["user_id"] = f"eq.{user.user_id}"
        return await rest_request("GET", "conversations", user.access_token, params=params)
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/support/conversations/{conversation_id}")
async def get_support_conversation(conversation_id: str, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        rows = await rest_request(
            "GET",
            "conversations",
            user.access_token,
            params={"id": f"eq.{conversation_id}", "select": "*,messages(*),support_tickets(*)", "limit": "1"},
        )
        if not rows:
            raise HTTPException(404, "Support conversation not found")
        return rows[0]
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/support/conversations/{conversation_id}/messages", status_code=201)
async def send_support_message(conversation_id: str, payload: SupportMessageCreate, user: Annotated[AuthContext, Depends(current_user)]):
    enforce_rate_limit(f"support-message:{user.user_id}", limit=30, window_seconds=60)
    sender_type = "admin" if user.role == "admin" else "customer"
    try:
        rows = await rest_request("POST", "messages", user.access_token, body={"conversation_id": conversation_id, "sender_id": user.user_id, "sender_type": sender_type, "content": payload.content}, prefer="return=representation")
        conversation_rows = await rest_request(
            "GET",
            "conversations",
            user.access_token,
            params={"id": f"eq.{conversation_id}", "select": "id,user_id,support_ticket_id", "limit": "1"},
        )
        if conversation_rows:
            conversation = conversation_rows[0]
            message_id = rows[0]["id"] if rows else conversation_id
            if sender_type == "admin":
                await notify_user(
                    conversation["user_id"],
                    notification_type="support.message",
                    title="Support replied to your request",
                    body=payload.content[:240],
                    data={"conversation_id": conversation_id},
                    dedupe_key=f"support-message:{message_id}",
                )
            else:
                await notify_admins(
                    notification_type="support.message",
                    title="New customer support message",
                    body=payload.content[:240],
                    data={"conversation_id": conversation_id, "ticket_id": conversation.get("support_ticket_id")},
                    dedupe_prefix=f"support-message:{message_id}",
                )
        return rows[0] if rows else None
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/support/conversations/{conversation_id}/read")
async def mark_support_conversation_read(conversation_id: str, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        count = await rpc_request("mark_conversation_read", user.access_token, {"p_conversation_id": conversation_id})
        return {"conversation_id": conversation_id, "marked_read": int(count or 0)}
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/support/conversations/{conversation_id}/handoff")
async def request_support_handoff(conversation_id: str, payload: SupportHandoffRequest, user: Annotated[AuthContext, Depends(current_user)]):
    if user.role == "admin":
        raise HTTPException(403, "Only customers can request AI-to-human handoff")
    try:
        conversation = await rpc_request(
            "request_human_handoff",
            user.access_token,
            {"p_conversation_id": conversation_id, "p_reason": payload.reason, "p_ai_context": payload.context},
        )
        await notify_admins(
            notification_type="support.handoff",
            title="AI handoff requested",
            body=payload.reason,
            data={"conversation_id": conversation_id},
            dedupe_prefix=f"support-handoff:{conversation_id}",
        )
        return conversation
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/support/conversations/{conversation_id}/close")
async def close_support_conversation(conversation_id: str, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        closed = await rpc_request("close_support_conversation", user.access_token, {"p_conversation_id": conversation_id})
        return {"conversation_id": conversation_id, "closed": bool(closed)}
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.patch("/admin/support/conversations/{conversation_id}")
async def update_support_conversation(conversation_id: str, payload: SupportConversationUpdate, user: Annotated[AuthContext, Depends(require_role("admin"))]):
    values = payload.model_dump(exclude_none=True)
    if not values:
        raise HTTPException(422, "At least one support field is required")
    try:
        conversations = await rest_request(
            "GET", "conversations", user.access_token,
            params={"id": f"eq.{conversation_id}", "select": "support_ticket_id", "limit": "1"},
        )
        if not conversations or not conversations[0].get("support_ticket_id"):
            raise HTTPException(404, "Support conversation not found")
        ticket_id = conversations[0]["support_ticket_id"]
        updated = await rest_request(
            "PATCH", "support_tickets", user.access_token,
            params={"id": f"eq.{ticket_id}"},
            body={**values, "updated_at": datetime.now(timezone.utc).isoformat()},
            prefer="return=representation",
        )
        return updated[0] if updated else {"id": ticket_id, **values}
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/notifications")
async def list_notifications(user: Annotated[AuthContext, Depends(current_user)]):
    try:
        return await rest_request("GET", "notifications", user.access_token, params={"user_id": f"eq.{user.user_id}", "order": "created_at.desc", "limit": "100"})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/notifications/unread-count")
async def unread_notification_count(user: Annotated[AuthContext, Depends(current_user)]):
    try:
        rows = await rest_request("GET", "notifications", user.access_token, params={"user_id": f"eq.{user.user_id}", "read_at": "is.null", "select": "id"})
        return {"unread_count": len(rows or [])}
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        marked = await rpc_request("mark_notification_read", user.access_token, {"p_notification_id": notification_id})
        if not marked:
            raise HTTPException(404, "Notification not found")
        return {"notification_id": notification_id, "read": True}
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/notifications/read-all")
async def mark_all_notifications_read(user: Annotated[AuthContext, Depends(current_user)]):
    try:
        count = await rpc_request("mark_all_notifications_read", user.access_token, {})
        return {"marked_read": int(count or 0)}
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/seller/discounts", status_code=201)
async def create_seller_discount(payload: DiscountCreate, user: Annotated[AuthContext, Depends(require_role("seller"))]):
    try:
        seller_id = await own_seller_id(user)
        rows = await rest_request("POST", "discounts", user.access_token, body={"seller_id": seller_id, "funded_by": "seller", **payload.model_dump()}, prefer="return=representation")
        return rows[0] if rows else None
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/seller-applications")
async def list_own_applications(user: Annotated[AuthContext, Depends(current_user)]):
    try:
        return await rest_request("GET", "seller_applications", _token_placeholder(user), params={"user_id": f"eq.{user.user_id}", "order": "created_at.desc"})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/admin/seller-applications")
async def admin_list_applications(user: Annotated[AuthContext, Depends(require_role("admin"))]):
    try:
        return await rest_request("GET", "seller_applications", _token_placeholder(user), params={"order": "created_at.desc"})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.patch("/admin/seller-applications/{application_id}")
async def admin_decide_application(application_id: str, payload: SellerApplicationDecision, user: Annotated[AuthContext, Depends(require_role("admin"))]):
    try:
        result = await rest_request("PATCH", "seller_applications", _token_placeholder(user), params={"id": f"eq.{application_id}", "status": "eq.pending"}, body={"status": payload.status, "rejection_reason": payload.rejection_reason, "reviewed_by": user.user_id, "reviewed_at": datetime.now(timezone.utc).isoformat()}, prefer="return=representation")
        return result[0] if result else None
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/admin/customers")
async def admin_customers(user: Annotated[AuthContext, Depends(require_role("admin"))]):
    try:
        return await privileged_request("GET", "profiles", params={"select": "id,full_name,phone,role,created_at,updated_at", "order": "created_at.desc"})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/admin/orders")
async def admin_orders(user: Annotated[AuthContext, Depends(require_role("admin"))], status_filter: str | None = Query(default=None, alias="status")):
    params = {"select": "*,order_items(*)", "order": "created_at.desc"}
    if status_filter:
        params["status"] = f"eq.{status_filter}"
    try:
        return await privileged_request("GET", "orders", params=params)
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/admin/transactions")
async def admin_transactions(user: Annotated[AuthContext, Depends(require_role("admin"))]):
    try:
        return {
            "payments": await privileged_request("GET", "payments", params={"select": "*", "order": "verified_at.desc.nullslast"}),
            "payment_attempts": await privileged_request("GET", "payment_attempts", params={"select": "*", "order": "created_at.desc"}),
            "refunds": await privileged_request("GET", "refunds", params={"select": "*", "order": "created_at.desc"}),
            "commissions": await privileged_request("GET", "commission_records", params={"select": "*", "order": "created_at.desc"}),
        }
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/admin/withdrawals")
async def admin_withdrawals(user: Annotated[AuthContext, Depends(require_role("admin"))]):
    try:
        return await privileged_request("GET", "withdrawal_requests", params={"select": "*,sellers(display_name,slug)", "order": "created_at.desc"})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/admin/analytics")
async def admin_analytics(user: Annotated[AuthContext, Depends(require_role("admin"))]):
    try:
        orders = await privileged_request("GET", "orders", params={"select": "id,status,total_pkr,created_at", "order": "created_at.desc"})
        payments = await privileged_request("GET", "payments", params={"select": "id,status,provider,order_id,verified_at"})
        commissions = await privileged_request("GET", "commission_records", params={"select": "basis_pkr,commission_pkr"})
        return {
            "orders": {"count": len(orders), "gross_pkr": sum(int(row.get("total_pkr") or 0) for row in orders if row.get("status") != "cancelled")},
            "payments": {"count": len(payments), "paid_count": sum(1 for row in payments if row.get("status") == "paid")},
            "commission": {"basis_pkr": sum(int(row.get("basis_pkr") or 0) for row in commissions), "commission_pkr": sum(int(row.get("commission_pkr") or 0) for row in commissions)},
        }
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.patch("/admin/orders/{order_id}")
async def admin_update_order(order_id: str, payload: AdminOrderStatus, user: Annotated[AuthContext, Depends(require_role("admin"))]):
    try:
        rows = await privileged_request("PATCH", "orders", params={"id": f"eq.{order_id}"}, body={"status": payload.status}, prefer="return=representation")
        return rows[0] if rows else None
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/products")
async def public_products(q: str | None = Query(default=None, min_length=2, max_length=100), category_id: str | None = None):
    params = {"active": "eq.true", "select": "id,name,slug,description,category_id,price_pkr,product_images(*),product_variants(*)", "order": "created_at.desc"}
    if q:
        safe_q = re.sub(r"[^\w\s-]", " ", q, flags=re.UNICODE).strip()
        if len(safe_q) >= 2:
            params["or"] = f"(name.ilike.*{safe_q}*,description.ilike.*{safe_q}*)"
    if category_id:
        params["category_id"] = f"eq.{category_id}"
    try:
        return await rest_request("GET", "products", "", params=params)
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/ai/search")
async def ai_search(payload: AssistantRequest, user: Annotated[AuthContext | None, Depends(optional_current_user)]):
    enforce_rate_limit(f"ai-search:{user.user_id if user else 'anonymous'}")
    intent, gemini_intent_used = await extract_search_intent(payload.query)
    try:
        catalog = await _ai_catalog(user, include_inventory=intent.in_stock)
        products = filter_catalog(catalog, intent)
        recommendations = outfit_recommendations(catalog, intent)
        if user:
            await rest_request("POST", "ai_search_logs", user.access_token, body={"user_id": user.user_id, "query": payload.query, "result_product_ids": [item["id"] for item in products]}, prefer="return=minimal")
        return {
            "query": payload.query,
            "intent": intent.as_dict(),
            "products": products[:30],
            "recommendations": recommendations,
            "provider": "gemini-intent" if gemini_intent_used else "catalog-rules",
            "fallback": not gemini_intent_used,
        }
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/ai/chat")
@router.post("/ai/assistant")
async def ai_assistant(payload: AssistantRequest, user: Annotated[AuthContext, Depends(current_user)]):
    enforce_rate_limit(f"ai-assistant:{user.user_id}")
    intent, _ = await extract_search_intent(payload.query)
    try:
        catalog = await _ai_catalog(user, include_inventory=intent.in_stock)
        products = filter_catalog(catalog, intent)
        orders = await rest_request("GET", "orders", user.access_token, params={"user_id": f"eq.{user.user_id}", "select": "id,status,created_at", "order": "created_at.desc", "limit": "5"}) if any(word in payload.query.lower() for word in ("order", "delivery", "shipment", "parcel")) else []
        conversation_id = payload.conversation_id
        if not conversation_id:
            conversations = await rest_request("POST", "ai_conversations", user.access_token, body={"user_id": user.user_id}, prefer="return=representation")
            conversation_id = conversations[0]["id"] if conversations else None
        history: list[dict] = []
        if conversation_id:
            conversations = await rest_request("GET", "ai_conversations", user.access_token, params={"id": f"eq.{conversation_id}", "user_id": f"eq.{user.user_id}", "select": "id,ai_messages(id,role,content,created_at)", "limit": "1"})
            if not conversations:
                raise HTTPException(404, "AI conversation not found")
            history = conversations[0].get("ai_messages") or []
        recommendations = outfit_recommendations(catalog, intent)
        reply, fallback = await grounded_assistant_reply(
            payload.query,
            products,
            order_context=orders,
            conversation_context=history,
            recommendation_context=recommendations,
        )
        if conversation_id:
            await rest_request("POST", "ai_messages", user.access_token, body=[
                {"conversation_id": conversation_id, "role": "user", "content": payload.query},
                {"conversation_id": conversation_id, "role": "assistant", "content": reply},
            ], prefer="return=minimal")
        handoff_suggested = any(
            phrase in payload.query.lower()
            for phrase in ("human", "agent", "representative", "support person", "real person", "insaan")
        )
        return {
            "conversation_id": conversation_id,
            "reply": reply,
            "fallback": fallback,
            "handoff_suggested": handoff_suggested,
            "products": products[:10],
            "recommendations": recommendations,
            "orders": orders,
        }
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/ai/conversations/{conversation_id}/handoff", status_code=201)
async def handoff_ai_conversation(conversation_id: str, payload: SupportHandoffRequest, user: Annotated[AuthContext, Depends(current_user)]):
    """Create a support conversation from an authenticated AI conversation without exposing AI history."""
    try:
        ai_rows = await rest_request(
            "GET",
            "ai_conversations",
            user.access_token,
            params={"id": f"eq.{conversation_id}", "user_id": f"eq.{user.user_id}", "select": "id,ai_messages(id,role,content,created_at)", "limit": "1"},
        )
        if not ai_rows:
            raise HTTPException(404, "AI conversation not found")
        existing = await rest_request(
            "GET",
            "conversations",
            user.access_token,
            params={"user_id": f"eq.{user.user_id}", "select": "*", "order": "created_at.desc", "limit": "50"},
        )
        for conversation in existing or []:
            if (conversation.get("ai_context") or {}).get("ai_conversation_id") == conversation_id:
                return conversation

        ticket_rows = await rest_request(
            "POST",
            "support_tickets",
            user.access_token,
            body={"user_id": user.user_id, "subject": "AI assistant handoff", "priority": "high"},
            prefer="return=representation",
        )
        ticket_id = ticket_rows[0]["id"]
        context = {
            **payload.context,
            "ai_conversation_id": conversation_id,
            "recent_messages": [
                {"role": item.get("role"), "content": str(item.get("content", ""))[:500]}
                for item in (ai_rows[0].get("ai_messages") or [])[-8:]
            ],
        }
        support_rows = await rest_request(
            "POST",
            "conversations",
            user.access_token,
            body={
                "user_id": user.user_id,
                "support_ticket_id": ticket_id,
                "handoff_requested": True,
                "handoff_reason": payload.reason,
                "handoff_at": datetime.now(timezone.utc).isoformat(),
                "ai_context": context,
            },
            prefer="return=representation",
        )
        support_conversation_id = support_rows[0]["id"]
        await notify_admins(
            notification_type="support.handoff",
            title="AI handoff requested",
            body=payload.reason,
            data={"conversation_id": support_conversation_id, "ai_conversation_id": conversation_id},
            dedupe_prefix=f"support-handoff:{support_conversation_id}",
        )
        return support_rows[0]
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/ai/outfit")
async def ai_outfit(payload: AssistantRequest, user: Annotated[AuthContext | None, Depends(optional_current_user)]):
    enforce_rate_limit(f"ai-outfit:{user.user_id if user else 'anonymous'}")
    intent, gemini_intent_used = await extract_search_intent(payload.query)
    try:
        catalog = await _ai_catalog(user, include_inventory=intent.in_stock)
        return {
            "query": payload.query,
            "intent": intent.as_dict(),
            "products": outfit_recommendations(catalog, intent),
            "provider": "gemini-intent" if gemini_intent_used else "catalog-rules",
            "fallback": not gemini_intent_used,
        }
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/ai/conversations")
async def list_ai_conversations(user: Annotated[AuthContext, Depends(current_user)]):
    try:
        return await rest_request("GET", "ai_conversations", user.access_token, params={"user_id": f"eq.{user.user_id}", "select": "id,locale,created_at", "order": "created_at.desc"})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/ai/conversations/{conversation_id}")
async def get_ai_conversation(conversation_id: str, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        rows = await rest_request("GET", "ai_conversations", user.access_token, params={"id": f"eq.{conversation_id}", "user_id": f"eq.{user.user_id}", "select": "id,locale,created_at,ai_messages(id,role,content,created_at)", "limit": "1"})
        if not rows:
            raise HTTPException(404, "AI conversation not found")
        return rows[0]
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.delete("/ai/conversations/{conversation_id}", status_code=204)
async def delete_ai_conversation(conversation_id: str, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        rows = await rest_request("GET", "ai_conversations", user.access_token, params={"id": f"eq.{conversation_id}", "user_id": f"eq.{user.user_id}", "select": "id", "limit": "1"})
        if not rows:
            raise HTTPException(404, "AI conversation not found")
        await rest_request("DELETE", "ai_conversations", user.access_token, params={"id": f"eq.{conversation_id}", "user_id": f"eq.{user.user_id}"})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/cart")
async def get_cart(user: Annotated[AuthContext, Depends(current_user)]):
    try:
        carts = await rest_request("GET", "shopping_carts", _token_placeholder(user), params={"user_id": f"eq.{user.user_id}", "status": "eq.active", "select": "id,status,created_at,cart_items(*)", "limit": "1"})
        return carts[0] if carts else {"status": "active", "cart_items": []}
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/cart/items", status_code=201)
async def add_cart_item(payload: CartItemCreate, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        carts = await rest_request("GET", "shopping_carts", _token_placeholder(user), params={"user_id": f"eq.{user.user_id}", "status": "eq.active", "select": "id", "limit": "1"})
        if carts:
            cart_id = carts[0]["id"]
        else:
            created = await rest_request("POST", "shopping_carts", _token_placeholder(user), body={"user_id": user.user_id, "status": "active"}, prefer="return=representation")
            cart_id = created[0]["id"]
        rows = await rest_request("POST", "cart_items", _token_placeholder(user), params={"on_conflict": "cart_id,variant_id"}, body={"cart_id": cart_id, **payload.model_dump()}, prefer="return=representation,resolution=merge-duplicates")
        return rows[0] if rows else None
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.delete("/cart/items/{item_id}", status_code=204)
async def remove_cart_item(item_id: str, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        await rest_request("DELETE", "cart_items", _token_placeholder(user), params={"id": f"eq.{item_id}"})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/orders")
async def list_own_orders(user: Annotated[AuthContext, Depends(current_user)]):
    try:
        return await rest_request("GET", "orders", _token_placeholder(user), params={"user_id": f"eq.{user.user_id}", "select": "*,order_items(*),payments(*)", "order": "created_at.desc"})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/orders/{order_id}/cancel")
async def cancel_own_order(order_id: str, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        return await rpc_request("cancel_order", _token_placeholder(user), {"p_order_id": order_id})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/wallet")
async def get_wallet(user: Annotated[AuthContext, Depends(current_user)]):
    try:
        wallets = await rest_request("GET", "wallets", _token_placeholder(user), params={"user_id": f"eq.{user.user_id}", "select": "id,balance_pkr,pending_balance_pkr,updated_at", "limit": "1"})
        if not wallets:
            return {"balance_pkr": 0, "available_balance_pkr": 0, "pending_balance_pkr": 0, "transactions": []}
        wallet = wallets[0]
        wallet["available_balance_pkr"] = wallet.get("balance_pkr", 0)
        wallet["transactions"] = await rest_request("GET", "wallet_transactions", _token_placeholder(user), params={"wallet_id": f"eq.{wallet['id']}", "order": "created_at.desc"})
        return wallet
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/wallet/transactions")
async def wallet_transactions(user: Annotated[AuthContext, Depends(current_user)]):
    try:
        wallets = await rest_request("GET", "wallets", user.access_token, params={"user_id": f"eq.{user.user_id}", "select": "id", "limit": "1"})
        if not wallets:
            return []
        return await rest_request("GET", "wallet_transactions", user.access_token, params={"wallet_id": f"eq.{wallets[0]['id']}", "order": "created_at.desc"})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/seller/earnings")
async def seller_earnings(user: Annotated[AuthContext, Depends(require_role("seller"))]):
    try:
        seller_id = await own_seller_id(user)
        return await rest_request("GET", "seller_earnings", _token_placeholder(user), params={"seller_id": f"eq.{seller_id}", "order": "created_at.desc"})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


async def _read_tryon_upload(file: UploadFile) -> tuple[bytes, str, str]:
    mime_type = (file.content_type or "").lower()
    content = await file.read(MAX_IMAGE_BYTES + 1)
    try:
        validated = validate_image(content, mime_type)
    except ImageValidationError as error:
        status = 413 if len(content) > MAX_IMAGE_BYTES else 415
        raise HTTPException(status, str(error)) from error
    return validated.content, validated.mime_type, validated.sha256


async def _read_3d_asset(file: UploadFile) -> tuple[bytes, str]:
    mime_type = (file.content_type or "").lower()
    allowed = {"model/gltf-binary", "model/gltf+json", "application/octet-stream"}
    if mime_type not in allowed:
        raise HTTPException(415, "Only GLB/GLTF 3D model files are supported")
    max_bytes = 50 * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(413, "3D asset must be 50 MB or smaller")
    if mime_type in {"model/gltf-binary", "application/octet-stream"}:
        if len(content) < 12 or content[:4] != b"glTF":
            raise HTTPException(415, "GLB header is invalid")
    else:
        try:
            document = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise HTTPException(415, "GLTF JSON is invalid") from error
        if not isinstance(document, dict) or not isinstance(document.get("asset"), dict):
            raise HTTPException(415, "GLTF asset metadata is missing")
    return content, mime_type


async def _create_tryon_upload(file: UploadFile, user: AuthContext) -> dict:
    content, mime_type, sha256 = await _read_tryon_upload(file)
    upload_id = str(uuid4())
    path = f"{user.user_id}/{upload_id}.{extension_for_mime(mime_type)}"
    try:
        duplicate = await rest_request(
            "GET", "tryon_uploads", user.access_token,
            params={"user_id": f"eq.{user.user_id}", "sha256": f"eq.{sha256}", "deleted_at": "is.null", "limit": "1"},
        )
        if duplicate:
            return duplicate[0]
        await storage_upload("tryon-private", path, user.access_token, content, mime_type)
        rows = await rest_request(
            "POST", "tryon_uploads", user.access_token,
            body={"id": upload_id, "user_id": user.user_id, "storage_path": path, "mime_type": mime_type, "byte_size": len(content), "sha256": sha256},
            prefer="return=representation",
        )
        return rows[0] if rows else {"id": upload_id, "storage_path": path, "mime_type": mime_type, "byte_size": len(content)}
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/tryon/upload", status_code=201)
async def upload_tryon_source(file: Annotated[UploadFile, File()], user: Annotated[AuthContext, Depends(current_user)]):
    enforce_rate_limit(f"tryon-upload:{user.user_id}", limit=5, window_seconds=3600)
    return await _create_tryon_upload(file, user)


@router.post("/tryon/jobs", status_code=202)
async def create_tryon_job(payload: TryOnJobCreate, user: Annotated[AuthContext, Depends(current_user)]):
    if not settings.tryon_provider_url or not settings.tryon_provider_api_key:
        raise HTTPException(503, "TRYON_PROVIDER_URL and TRYON_PROVIDER_API_KEY are required; live try-on is unavailable")
    enforce_rate_limit(f"tryon-job:{user.user_id}", limit=10, window_seconds=3600)
    try:
        uploads = await rest_request(
            "GET", "tryon_uploads", user.access_token,
            params={"id": f"eq.{payload.upload_id}", "user_id": f"eq.{user.user_id}", "deleted_at": "is.null", "expires_at": "gt.{datetime.now(timezone.utc).isoformat()}", "limit": "1"},
        )
        if not uploads:
            raise HTTPException(404, "Try-on upload not found or expired")
        products = await rest_request("GET", "products", user.access_token, params={"id": f"eq.{payload.product_id}", "active": "eq.true", "select": "id", "limit": "1"})
        if not products:
            raise HTTPException(404, "Active product not found")
        rows = await rest_request(
            "POST", "ai_tryon_jobs", user.access_token,
            body={"user_id": user.user_id, "product_id": payload.product_id, "source_image_path": uploads[0]["storage_path"], "status": "pending"},
            prefer="return=representation",
        )
        return rows[0] if rows else {"status": "pending"}
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/ai/try-on", status_code=202)
async def create_legacy_try_on_job(product_id: str, file: Annotated[UploadFile, File()], user: Annotated[AuthContext, Depends(current_user)]):
    if not settings.tryon_provider_url or not settings.tryon_provider_api_key:
        raise HTTPException(503, "TRYON_PROVIDER_URL and TRYON_PROVIDER_API_KEY are required; live try-on is unavailable")
    upload = await _create_tryon_upload(file, user)
    return await create_tryon_job(TryOnJobCreate(upload_id=upload["id"], product_id=product_id), user)


@router.get("/tryon/jobs/{job_id}")
@router.get("/ai/try-on/{job_id}")
async def get_try_on_job(job_id: str, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        rows = await rest_request("GET", "ai_tryon_jobs", user.access_token, params={"id": f"eq.{job_id}", "user_id": f"eq.{user.user_id}", "limit": "1"})
        if not rows:
            raise HTTPException(404, "Try-on job not found")
        return rows[0]
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/tryon/jobs/{job_id}/result")
@router.get("/ai/try-on/{job_id}/result")
async def get_try_on_result_url(job_id: str, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        rows = await rest_request("GET", "ai_tryon_jobs", user.access_token, params={"id": f"eq.{job_id}", "user_id": f"eq.{user.user_id}", "status": "eq.completed", "select": "result_image_path", "limit": "1"})
        if not rows or not rows[0].get("result_image_path"):
            raise HTTPException(404, "Completed try-on result not found")
        url = await storage_signed_url("tryon-private", rows[0]["result_image_path"], user.access_token)
        if not url:
            raise HTTPException(502, "Could not create signed result URL")
        return {"url": url, "expires_in": 300}
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.delete("/tryon/jobs/{job_id}", status_code=204)
@router.delete("/ai/try-on/{job_id}", status_code=204)
async def delete_try_on_job(job_id: str, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        rows = await rest_request("GET", "ai_tryon_jobs", user.access_token, params={"id": f"eq.{job_id}", "user_id": f"eq.{user.user_id}", "limit": "1"})
        if not rows:
            raise HTTPException(404, "Try-on job not found")
        job = rows[0]
        for path in (job.get("source_image_path"), job.get("result_image_path")):
            if path and path != "deleted":
                await storage_delete("tryon-private", path, user.access_token)
        await rest_request("PATCH", "ai_tryon_jobs", user.access_token, params={"id": f"eq.{job_id}", "user_id": f"eq.{user.user_id}"}, body={"status": "cancelled", "source_image_path": "deleted", "result_image_path": None})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.delete("/tryon/uploads/{upload_id}", status_code=204)
async def delete_tryon_upload(upload_id: str, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        uploads = await rest_request("GET", "tryon_uploads", user.access_token, params={"id": f"eq.{upload_id}", "user_id": f"eq.{user.user_id}", "deleted_at": "is.null", "limit": "1"})
        if not uploads:
            raise HTTPException(404, "Try-on upload not found")
        upload = uploads[0]
        active_jobs = await rest_request("GET", "ai_tryon_jobs", user.access_token, params={"source_image_path": f"eq.{upload['storage_path']}", "status": "in.(pending,processing)", "limit": "1"})
        if active_jobs:
            raise HTTPException(409, "Upload is being used by an active try-on job")
        await storage_delete("tryon-private", upload["storage_path"], user.access_token)
        await rest_request("PATCH", "tryon_uploads", user.access_token, params={"id": f"eq.{upload_id}", "user_id": f"eq.{user.user_id}"}, body={"deleted_at": datetime.now(timezone.utc).isoformat()})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/checkout", status_code=201)
async def checkout(payload: CheckoutCreate, user: Annotated[AuthContext, Depends(current_user)]):
    enforce_rate_limit(f"checkout:{user.user_id}", limit=10, window_seconds=60)
    try:
        order = await rpc_request("create_order", _token_placeholder(user), {
            "p_idempotency_key": payload.idempotency_key,
            "p_address_id": payload.address_id,
            "p_items": [item.model_dump() for item in payload.items],
            "p_delivery_pkr": payload.delivery_pkr,
            "p_discount_pkr": payload.discount_pkr,
        })
        order_record = order[0] if isinstance(order, list) and order else order
        if isinstance(order_record, dict):
            await deliver_new_order(order_record, user.user_id, [item.model_dump() for item in payload.items], user.access_token)
        return order
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/payments/initiate", status_code=202)
async def initiate_payment(payload: PaymentInitiate, user: Annotated[AuthContext, Depends(current_user)]):
    enforce_rate_limit(f"payment-initiate:{user.user_id}", limit=10, window_seconds=60)
    try:
        ensure_provider_configured(payload.provider)
        idempotency_key = payload.idempotency_key.strip() or f"payment:{payload.order_id}:{payload.provider}"
        attempt = await rpc_request("begin_payment_attempt", user.access_token, {
            "p_order_id": payload.order_id,
            "p_provider": payload.provider,
            "p_idempotency_key": idempotency_key,
        })
        if isinstance(attempt, list):
            attempt = attempt[0] if attempt else None
        if not isinstance(attempt, dict):
            raise HTTPException(502, "Payment attempt could not be created")
        transaction_ref = str(attempt["id"]).replace("-", "")[:20]
        if payload.provider == "jazzcash":
            form = JazzCashAdapter().build_checkout_form(
                amount_pkr=int(attempt["amount_pkr"]),
                transaction_ref=transaction_ref,
                bill_reference=str(attempt["payment_id"]),
                description=f"Zarma Store order {payload.order_id}",
            )
            return {
                "payment_id": attempt["payment_id"], "attempt_id": attempt["id"], "provider": payload.provider,
                "status": attempt["status"], "amount_pkr": attempt["amount_pkr"], "currency": "PKR",
                "checkout": {"action_url": form.action_url, "fields": form.fields},
                "live_provider_enabled": True, "sandbox_verified": False,
            }
        raise PaymentProviderUnavailable("Easypaisa live checkout remains disabled until the official merchant contract is verified")
    except PaymentProviderUnavailable as error:
        raise HTTPException(503, str(error)) from error
    except ValueError as error:
        raise HTTPException(502, str(error)) from error
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.get("/payments/{payment_id}")
async def payment_status(payment_id: str, user: Annotated[AuthContext, Depends(current_user)]):
    try:
        rows = await rest_request("GET", "payments", user.access_token, params={"id": f"eq.{payment_id}", "select": "id,order_id,status,provider,provider_reference,verified_at,orders!inner(user_id)", "orders.user_id": f"eq.{user.user_id}", "limit": "1"})
        if not rows:
            raise HTTPException(404, "Payment not found")
        return rows[0]
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/payments/{provider}/callback")
async def payment_callback(provider: str, event: PaymentCallback, request: Request):
    if provider not in {"jazzcash", "easypaisa"}:
        raise HTTPException(404, "Unsupported payment provider")
    client_host = request.client.host if request.client else "unknown"
    enforce_rate_limit(f"payment-callback:{provider}:{client_host}", limit=60, window_seconds=60)
    try:
        ensure_provider_configured(provider)
        if not verify_callback(provider, canonical_payload(event.payload), event.signature):
            raise HTTPException(401, "Invalid payment callback signature")
        payload_status = str(event.payload.get("status") or event.payload.get("payment_status") or "").lower()
        response_code = str(event.payload.get("pp_ResponseCode") or event.payload.get("pp_ResponseCode") or "")
        is_refund = "refund" in event.event_type.lower()
        if is_refund:
            callback_status = "refunded"
        elif provider == "jazzcash" and response_code == "000":
            callback_status = "paid"
        elif payload_status in {"paid", "success", "successful", "completed"}:
            callback_status = "paid"
        elif payload_status in {"failed", "failure", "cancelled", "expired"} or response_code:
            callback_status = "failed"
        else:
            callback_status = "pending"
        amount_raw = event.payload.get("pp_Amount") or event.payload.get("amount") or event.payload.get("amount_pkr")
        amount_pkr = int(amount_raw) if amount_raw is not None and str(amount_raw).isdigit() else None
        provider_event_id = str(event.payload.get("pp_TxnRefNo") or event.payload.get("transaction_id") or event.provider_event_id)
        token = settings.supabase_service_role_key
        if not token:
            raise HTTPException(503, "SUPABASE_SERVICE_ROLE_KEY is required to process trusted payment callbacks")
        return await privileged_rpc_request("process_payment_event", {
            "p_payment_id": event.payment_id,
            "p_provider": provider,
            "p_provider_event_id": provider_event_id,
            "p_event_type": event.event_type,
            "p_status": callback_status,
            "p_provider_reference": event.provider_reference or provider_event_id,
            "p_amount_pkr": amount_pkr,
            "p_payload": event.payload,
        })
    except PaymentProviderUnavailable as error:
        raise HTTPException(503, str(error)) from error
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/payments/{payment_id}/refund", status_code=202)
async def request_payment_refund(payment_id: str, payload: RefundCreate, user: Annotated[AuthContext, Depends(require_role("admin"))]):
    enforce_rate_limit(f"refund-request:{user.user_id}", limit=20, window_seconds=60)
    try:
        payment = await privileged_request("GET", "payments", params={"id": f"eq.{payment_id}", "select": "id,provider,status", "limit": "1"})
        if not payment:
            raise HTTPException(404, "Payment not found")
        ensure_provider_configured(payment[0]["provider"])
        refund = await rpc_request("create_refund_request", user.access_token, {
            "p_payment_id": payment_id,
            "p_amount_pkr": payload.amount_pkr,
            "p_idempotency_key": payload.idempotency_key,
            "p_reason": payload.reason,
        })
        return {"refund": refund, "provider_submission": "pending_provider_verification"}
    except PaymentProviderUnavailable as error:
        raise HTTPException(503, str(error)) from error
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/seller/withdrawals", status_code=201)
async def create_withdrawal(payload: WithdrawalCreate, user: Annotated[AuthContext, Depends(require_role("seller"))]):
    enforce_rate_limit(f"withdrawal:{user.user_id}", limit=5, window_seconds=3600)
    try:
        return await rpc_request("request_seller_withdrawal", _token_placeholder(user), {"p_amount_pkr": payload.amount_pkr, "p_payout_method": payload.payout_method, "p_payout_reference": payload.payout_reference, "p_idempotency_key": payload.idempotency_key})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.patch("/admin/withdrawals/{withdrawal_id}")
async def update_withdrawal(withdrawal_id: str, payload: WithdrawalDecision, user: Annotated[AuthContext, Depends(require_role("admin"))]):
    try:
        result = await rpc_request("admin_set_withdrawal_status", user.access_token, {
            "p_withdrawal_id": withdrawal_id,
            "p_status": payload.status,
            "p_payout_reference": payload.payout_reference,
        })
        return result
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/seller/products", status_code=201)
async def create_product(payload: ProductCreate, user: Annotated[AuthContext, Depends(require_role("seller", "admin"))]):
    try:
        seller_id = payload.seller_id if user.role == "admin" else await own_seller_id(user)
        if not seller_id:
            raise HTTPException(400, "seller_id is required for admin-created products")
        product_data = payload.model_dump(exclude={"seller_id"})
        rows = await rest_request("POST", "products", _token_placeholder(user), body={"seller_id": seller_id, **product_data}, prefer="return=representation")
        return rows[0] if rows else None
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.patch("/seller/products/{product_id}")
async def update_product(product_id: str, payload: ProductUpdate, user: Annotated[AuthContext, Depends(require_role("seller", "admin"))]):
    try:
        params = {"id": f"eq.{product_id}"} if user.role == "admin" else {"id": f"eq.{product_id}", "seller_id": f"eq.{await own_seller_id(user)}"}
        rows = await rest_request("PATCH", "products", _token_placeholder(user), params=params, body=payload.model_dump(exclude={"seller_id"}), prefer="return=representation")
        return rows[0] if rows else None
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.delete("/seller/products/{product_id}", status_code=204)
async def archive_product(product_id: str, user: Annotated[AuthContext, Depends(require_role("seller", "admin"))]):
    try:
        params = {"id": f"eq.{product_id}"} if user.role == "admin" else {"id": f"eq.{product_id}", "seller_id": f"eq.{await own_seller_id(user)}"}
        await rest_request("PATCH", "products", _token_placeholder(user), params=params, body={"active": False})
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


async def assert_product_access(product_id: str, user: AuthContext) -> str | None:
    params = {"id": f"eq.{product_id}", "select": "id,seller_id", "limit": "1"}
    if user.role != "admin":
        params["seller_id"] = f"eq.{await own_seller_id(user)}"
    rows = await rest_request("GET", "products", _token_placeholder(user), params=params)
    if not rows:
        raise HTTPException(404, "Product not found or not owned by seller")
    return rows[0].get("seller_id")


@router.post("/seller/products/{product_id}/variants", status_code=201)
async def create_variant(product_id: str, payload: VariantCreate, user: Annotated[AuthContext, Depends(require_role("seller", "admin"))]):
    try:
        await assert_product_access(product_id, user)
        variants = await rest_request("POST", "product_variants", _token_placeholder(user), body={"product_id": product_id, "sku": payload.sku, "size": payload.size, "color": payload.color, "price_pkr": payload.price_pkr}, prefer="return=representation")
        variant = variants[0] if variants else None
        if not variant:
            raise HTTPException(502, "Variant was not created")
        await rest_request("POST", "inventory", _token_placeholder(user), body={"variant_id": variant["id"], "quantity": payload.quantity, "reserved_quantity": 0}, prefer="return=minimal")
        return variant
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.patch("/seller/variants/{variant_id}/inventory")
async def adjust_variant_inventory(variant_id: str, payload: InventoryAdjustment, user: Annotated[AuthContext, Depends(require_role("seller", "admin"))]):
    if payload.quantity_delta == 0:
        raise HTTPException(422, "quantity_delta cannot be zero")
    try:
        result = await rpc_request("adjust_inventory", _token_placeholder(user), {"p_variant_id": variant_id, "p_quantity_delta": payload.quantity_delta, "p_reason": payload.reason})
        return result
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/seller/products/{product_id}/images", status_code=201)
async def upload_product_image(product_id: str, file: Annotated[UploadFile, File()], user: Annotated[AuthContext, Depends(require_role("seller", "admin"))]):
    enforce_rate_limit(f"seller-image-upload:{user.user_id}", limit=30, window_seconds=3600)
    try:
        seller_id = await assert_product_access(product_id, user)
        content = await file.read(MAX_IMAGE_BYTES + 1)
        try:
            validated = validate_image(content, (file.content_type or "").lower())
        except ImageValidationError as error:
            status = 413 if len(content) > MAX_IMAGE_BYTES else 415
            raise HTTPException(status, str(error)) from error
        path = f"{seller_id or 'admin'}/{product_id}/{uuid4()}.{extension_for_mime(validated.mime_type)}"
        await storage_upload("product-media", path, _token_placeholder(user), validated.content, validated.mime_type)
        rows = await rest_request("POST", "product_images", _token_placeholder(user), body={"product_id": product_id, "storage_path": path, "alt_text": (file.filename or "")[:160], "sort_order": 0}, prefer="return=representation")
        return rows[0] if rows else {"storage_path": path}
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


@router.post("/seller/products/{product_id}/3d-assets", status_code=201)
async def upload_product_3d_asset(product_id: str, file: Annotated[UploadFile, File()], user: Annotated[AuthContext, Depends(require_role("seller", "admin"))]):
    allowed = {"model/gltf-binary": ".glb", "model/gltf+json": ".gltf", "application/octet-stream": ".glb"}
    enforce_rate_limit(f"seller-3d-upload:{user.user_id}", limit=10, window_seconds=3600)
    try:
        seller_id = await assert_product_access(product_id, user)
        content, mime_type = await _read_3d_asset(file)
        path = f"{seller_id or 'admin'}/{product_id}/{uuid4()}{allowed[mime_type]}"
        await storage_upload("product-3d", path, _token_placeholder(user), content, mime_type)
        rows = await rest_request("POST", "product_3d_assets", _token_placeholder(user), body={"product_id": product_id, "storage_path": path, "file_type": mime_type, "file_size_bytes": len(content)}, prefer="return=representation")
        return rows[0] if rows else {"storage_path": path}
    except SupabaseRestError as error:
        raise HTTPException(error.status_code, error.detail) from error


async def own_seller_id(user: AuthContext) -> str:
    rows = await rest_request("GET", "sellers", _token_placeholder(user), params={"user_id": f"eq.{user.user_id}", "select": "id", "limit": "1"})
    if not rows:
        raise HTTPException(403, "Approved seller account required")
    return rows[0]["id"]


def _token_placeholder(user: AuthContext) -> str:
    return user.access_token
