# n8n exports

Import the JSON files into n8n, then set the webhook URLs and environment variables in the n8n instance. These workflows are notification helpers only: order creation, payment verification, and stock reservation remain server/database responsibilities.

Planned exports: new order, customer confirmation, low stock, out of stock, order status, daily sales summary, and AI escalation. The first import-ready workflow is included as `new-order.json`; the remaining event contracts should be added once the production email/SMS provider is selected.
