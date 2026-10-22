from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    frontend_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    metrics_token: str = ""
    currency: str = "PKR"
    commission_rate: str = "0.10"
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_service_role_key: str = ""
    supabase_secret_key: str = ""
    gemini_api_key: str = ""
    gemini_api_url: str = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    gemini_model: str = "gemini-3.5-flash-lite"
    ai_timeout_seconds: float = 20.0
    tryon_provider_url: str = ""
    tryon_provider_api_key: str = ""
    jazzcash_merchant_id: str = ""
    jazzcash_password: str = ""
    jazzcash_shared_secret: str = ""
    jazzcash_checkout_url: str = "https://sandbox.jazzcash.com.pk/CustomerPortal/transactionmanagement/merchantform/"
    jazzcash_return_url: str = ""
    jazzcash_callback_secret: str = ""
    easypaisa_merchant_id: str = ""
    easypaisa_store_id: str = ""
    easypaisa_api_url: str = ""
    easypaisa_contract_verified: bool = False
    easypaisa_callback_secret: str = ""
    n8n_order_webhook_url: str = ""
    n8n_customer_registered_webhook_url: str = ""
    n8n_webhook_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
