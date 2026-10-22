import { createClient } from "@/lib/supabase/client";

export type BackendVariant = {
  id: string;
  sku?: string;
  size?: string;
  color?: string;
  price_pkr?: number;
  stock?: number;
  quantity?: number;
  active?: boolean;
};

export type BackendProduct = {
  id: string;
  name: string;
  slug?: string;
  description?: string | null;
  category_id?: string | null;
  price_pkr?: number;
  active?: boolean;
  product_images?: Array<Record<string, unknown>>;
  product_variants?: BackendVariant[];
};

export type AiSearchResult = {
  query?: string;
  products?: BackendProduct[];
  recommendations?: BackendProduct[];
  fallback?: boolean;
  [key: string]: unknown;
};

export type AiAssistantResult = {
  answer?: string;
  message?: string;
  products?: BackendProduct[];
  recommendations?: BackendProduct[];
  conversation_id?: string;
  [key: string]: unknown;
};

export type BackendRequestInit = RequestInit & { auth?: boolean };

export class BackendApiError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, payload: unknown) {
    super(typeof payload === "object" && payload && "detail" in payload ? String((payload as { detail: unknown }).detail) : `Backend request failed (${status})`);
    this.name = "BackendApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function backendBaseUrl() {
  return (process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
}

async function accessToken() {
  if (typeof window === "undefined") return null;
  const { data } = await createClient().auth.getSession();
  return data.session?.access_token ?? null;
}

export async function backendRequest<T>(path: string, init: BackendRequestInit = {}): Promise<T> {
  const { auth = true, headers, body, ...request } = init;
  const requestHeaders = new Headers(headers);
  if (body && !requestHeaders.has("Content-Type") && !(body instanceof FormData)) requestHeaders.set("Content-Type", "application/json");
  if (auth) {
    const token = await accessToken();
    if (token) requestHeaders.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${backendBaseUrl()}${path}`, { ...request, body, headers: requestHeaders, credentials: "include" });
  const contentType = response.headers.get("content-type") || "";
  const payload: unknown = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) throw new BackendApiError(response.status, payload);
  return payload as T;
}

export const backend = {
  health: () => backendRequest<{ status: string; service: string }>("/health", { auth: false }),
  config: () => backendRequest<{ currency: string; commission_rate: string }>("/api/v1/config", { auth: false }),
  customerRegistered: (payload: { full_name?: string | null }) => backendRequest<{ accepted: boolean; event_type: string }>("/api/v1/auth/customer-registered", { method: "POST", body: JSON.stringify(payload) }),
  products: (params?: { q?: string; categoryId?: string }) => {
    const query = new URLSearchParams();
    if (params?.q) query.set("q", params.q);
    if (params?.categoryId) query.set("category_id", params.categoryId);
    return backendRequest<BackendProduct[]>(`/api/v1/products${query.size ? `?${query}` : ""}`, { auth: false });
  },
  aiSearch: (query: string) => backendRequest<AiSearchResult>("/api/v1/ai/search", { method: "POST", body: JSON.stringify({ query }) }),
  aiAssistant: (query: string, conversationId?: string) => backendRequest<AiAssistantResult>("/api/v1/ai/assistant", { method: "POST", body: JSON.stringify({ query, conversation_id: conversationId }) }),
  conversations: () => backendRequest<unknown[]>("/api/v1/ai/conversations"),
  conversation: (id: string) => backendRequest<unknown>(`/api/v1/ai/conversations/${encodeURIComponent(id)}`),
  deleteConversation: (id: string) => backendRequest<void>(`/api/v1/ai/conversations/${encodeURIComponent(id)}`, { method: "DELETE" }),
  outfit: (query: string) => backendRequest<AiSearchResult>("/api/v1/ai/outfit", { method: "POST", body: JSON.stringify({ query }) }),
  handoffConversation: (id: string) => backendRequest<unknown>(`/api/v1/ai/conversations/${encodeURIComponent(id)}/handoff`, { method: "POST" }),
  cart: () => backendRequest<unknown>("/api/v1/cart"),
  addCartItem: (variantId: string, quantity = 1) => backendRequest<unknown>("/api/v1/cart/items", { method: "POST", body: JSON.stringify({ variant_id: variantId, quantity }) }),
  removeCartItem: (itemId: string) => backendRequest<void>(`/api/v1/cart/items/${encodeURIComponent(itemId)}`, { method: "DELETE" }),
  checkout: async (payload: { idempotency_key: string; address_id: string; items: Array<{ variant_id: string; quantity: number }>; delivery_pkr?: number; discount_pkr?: number }) => {
    const result = await backendRequest<{ order?: { id?: string; order_id?: string } }>("/api/v1/checkout", { method: "POST", body: JSON.stringify(payload) });
    if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("zarma:order-created", { detail: result }));
    return result;
  },
  profile: () => backendRequest<unknown>("/api/v1/me"),
  updateProfile: (payload: Record<string, unknown>) => backendRequest<unknown>("/api/v1/me", { method: "PATCH", body: JSON.stringify(payload) }),
  customSizes: (payload?: Record<string, unknown>) => payload ? backendRequest<unknown>("/api/v1/me/custom-sizes", { method: "POST", body: JSON.stringify(payload) }) : backendRequest<unknown[]>("/api/v1/me/custom-sizes"),
  orders: () => backendRequest<unknown[]>("/api/v1/orders"),
  cancelOrder: (id: string) => backendRequest<unknown>(`/api/v1/orders/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  wishlist: () => backendRequest<unknown[]>("/api/v1/wishlist"),
  toggleWishlist: (productId: string, remove = false) => backendRequest<unknown>(`/api/v1/wishlist/${encodeURIComponent(productId)}`, { method: remove ? "DELETE" : "POST" }),
  reviews: (productId: string) => backendRequest<unknown[]>(`/api/v1/products/${encodeURIComponent(productId)}/reviews`, { auth: false }),
  createReview: (payload: Record<string, unknown>) => backendRequest<unknown>("/api/v1/reviews", { method: "POST", body: JSON.stringify(payload) }),
  notifications: () => backendRequest<unknown[]>("/api/v1/notifications"),
  unreadNotifications: () => backendRequest<unknown>("/api/v1/notifications/unread-count"),
  markNotificationRead: (id: string) => backendRequest<void>(`/api/v1/notifications/${encodeURIComponent(id)}/read`, { method: "POST" }),
  markAllNotificationsRead: () => backendRequest<void>("/api/v1/notifications/read-all", { method: "POST" }),
  wallet: () => backendRequest<unknown>("/api/v1/wallet"),
  walletTransactions: () => backendRequest<unknown[]>("/api/v1/wallet/transactions"),
  supportConversations: () => backendRequest<unknown[]>("/api/v1/support/conversations"),
  supportConversation: (id: string) => backendRequest<unknown>(`/api/v1/support/conversations/${encodeURIComponent(id)}`),
  supportMessages: (id: string, payload: Record<string, unknown>) => backendRequest<unknown>(`/api/v1/support/conversations/${encodeURIComponent(id)}/messages`, { method: "POST", body: JSON.stringify(payload) }),
  closeSupport: (id: string) => backendRequest<void>(`/api/v1/support/conversations/${encodeURIComponent(id)}/close`, { method: "POST" }),
  handoffSupport: (id: string) => backendRequest<unknown>(`/api/v1/support/conversations/${encodeURIComponent(id)}/handoff`, { method: "POST" }),
  markSupportRead: (id: string) => backendRequest<void>(`/api/v1/support/conversations/${encodeURIComponent(id)}/read`, { method: "POST" }),
  createSupportConversation: (payload: Record<string, unknown>) => backendRequest<unknown>("/api/v1/support/conversations", { method: "POST", body: JSON.stringify(payload) }),
  tryonJobs: () => backendRequest<unknown[]>("/api/v1/tryon/jobs"),
  createTryonJob: (payload: Record<string, unknown>) => backendRequest<unknown>("/api/v1/tryon/jobs", { method: "POST", body: JSON.stringify(payload) }),
  uploadTryonImage: (form: FormData) => backendRequest<unknown>("/api/v1/tryon/upload", { method: "POST", body: form }),
  tryonJob: (id: string) => backendRequest<unknown>(`/api/v1/tryon/jobs/${encodeURIComponent(id)}`),
  deleteTryonJob: (id: string) => backendRequest<void>(`/api/v1/tryon/jobs/${encodeURIComponent(id)}`, { method: "DELETE" }),
  tryonResult: (id: string) => backendRequest<unknown>(`/api/v1/tryon/jobs/${encodeURIComponent(id)}/result`),
  deleteTryonUpload: (id: string) => backendRequest<void>(`/api/v1/tryon/uploads/${encodeURIComponent(id)}`, { method: "DELETE" }),
  initiatePayment: (payload: Record<string, unknown>) => backendRequest<unknown>("/api/v1/payments/initiate", { method: "POST", body: JSON.stringify(payload) }),
  payment: (id: string) => backendRequest<unknown>(`/api/v1/payments/${encodeURIComponent(id)}`),
  refundPayment: (id: string, payload: Record<string, unknown>) => backendRequest<unknown>(`/api/v1/payments/${encodeURIComponent(id)}/refund`, { method: "POST", body: JSON.stringify(payload) }),
  sellerApplications: () => backendRequest<unknown[]>("/api/v1/seller-applications"),
  applyAsSeller: (payload: Record<string, unknown>) => backendRequest<unknown>("/api/v1/seller-applications", { method: "POST", body: JSON.stringify(payload) }),
};

export const sellerBackend = {
  createProduct: (payload: Record<string, unknown>) => backendRequest<unknown>("/api/v1/seller/products", { method: "POST", body: JSON.stringify(payload) }),
  updateProduct: (id: string, payload: Record<string, unknown>) => backendRequest<unknown>(`/api/v1/seller/products/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteProduct: (id: string) => backendRequest<void>(`/api/v1/seller/products/${encodeURIComponent(id)}`, { method: "DELETE" }),
  addVariant: (productId: string, payload: Record<string, unknown>) => backendRequest<unknown>(`/api/v1/seller/products/${encodeURIComponent(productId)}/variants`, { method: "POST", body: JSON.stringify(payload) }),
  updateInventory: (variantId: string, payload: Record<string, unknown>) => backendRequest<unknown>(`/api/v1/seller/variants/${encodeURIComponent(variantId)}/inventory`, { method: "PATCH", body: JSON.stringify(payload) }),
  uploadProductImage: (productId: string, form: FormData) => backendRequest<unknown>(`/api/v1/seller/products/${encodeURIComponent(productId)}/images`, { method: "POST", body: form }),
  uploadProductAsset: (productId: string, form: FormData) => backendRequest<unknown>(`/api/v1/seller/products/${encodeURIComponent(productId)}/3d-assets`, { method: "POST", body: form }),
  createDiscount: (payload: Record<string, unknown>) => backendRequest<unknown>("/api/v1/seller/discounts", { method: "POST", body: JSON.stringify(payload) }),
  earnings: () => backendRequest<unknown>("/api/v1/seller/earnings"),
  requestWithdrawal: (payload: Record<string, unknown>) => backendRequest<unknown>("/api/v1/seller/withdrawals", { method: "POST", body: JSON.stringify(payload) }),
};

export const adminBackend = {
  analytics: () => backendRequest<unknown>("/api/v1/admin/analytics"),
  customers: () => backendRequest<unknown[]>("/api/v1/admin/customers"),
  orders: () => backendRequest<unknown[]>("/api/v1/admin/orders"),
  sellerApplications: () => backendRequest<unknown[]>("/api/v1/admin/seller-applications"),
  transactions: () => backendRequest<unknown[]>("/api/v1/admin/transactions"),
  withdrawals: () => backendRequest<unknown[]>("/api/v1/admin/withdrawals"),
  supportConversations: () => backendRequest<unknown[]>("/api/v1/admin/support/conversations"),
  updateOrder: (id: string, payload: Record<string, unknown>) => backendRequest<unknown>(`/api/v1/admin/orders/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  decideSellerApplication: (id: string, payload: Record<string, unknown>) => backendRequest<unknown>(`/api/v1/admin/seller-applications/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  updateSupportConversation: (id: string, payload: Record<string, unknown>) => backendRequest<unknown>(`/api/v1/admin/support/conversations/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  decideWithdrawal: (id: string, payload: Record<string, unknown>) => backendRequest<unknown>(`/api/v1/admin/withdrawals/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
};
