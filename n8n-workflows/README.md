# n8n exports

Import the JSON files into n8n, then set the webhook URLs and environment variables in the n8n instance. These workflows are notification helpers only: order creation, payment verification, and stock reservation remain server/database responsibilities.

Import `new-order-secure.json` for the signed order flow. In n8n, create a Header Auth credential named `Zarma webhook secret` with header name `X-Zarma-Webhook-Secret` and the same value as `N8N_WEBHOOK_SECRET`; configure the SMTP credential named `Zarma SMTP`, `ORDER_FROM_EMAIL`, and `ORDER_MANAGER_EMAIL`. The backend signs the raw JSON with HMAC-SHA256 in `X-Zarma-Signature`, and the Header Auth credential protects the endpoint. Keep the workflow inactive until a test request succeeds.

The older `new-order.json` is preserved as a legacy export. Planned exports include customer confirmation, low stock, out of stock, order status, daily sales summary, and AI escalation.
