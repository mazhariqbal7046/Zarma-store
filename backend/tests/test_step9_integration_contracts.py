from pathlib import Path

from app.ai_assistant import outfit_recommendations, parse_search_intent


ROOT = Path(__file__).resolve().parents[2]
STEP9_MIGRATION = ROOT / "supabase" / "migrations" / "20261019192238_step9_financial_storage_hardening.sql"
STORAGE_FIX = ROOT / "supabase" / "migrations" / "20261019192334_step9_storage_path_qualification_fix.sql"


def test_outfit_recommendations_prioritize_explicit_query_matches():
    catalog = [
        {"id": "red-shirt", "name": "Red Shirt", "active": True, "price_pkr": 1800, "product_variants": [{"size": "M", "color": "Red", "inventory": {"quantity": 1, "reserved_quantity": 0}}]},
        {"id": "black-shirt", "name": "Black Shirt", "active": True, "price_pkr": 2500, "product_variants": [{"size": "M", "color": "Black", "inventory": {"quantity": 1, "reserved_quantity": 0}}]},
        {"id": "black-trouser", "name": "Black Trouser", "active": True, "price_pkr": 2800, "product_variants": [{"size": "M", "color": "Black", "inventory": {"quantity": 1, "reserved_quantity": 0}}]},
    ]
    result = outfit_recommendations(catalog, parse_search_intent("black shirt"))
    assert [item["id"] for item in result[:2]] == ["black-shirt", "black-trouser"]


def test_step9_financial_and_storage_guards_are_migrated():
    financial = STEP9_MIGRATION.read_text(encoding="utf-8")
    storage = STORAGE_FIX.read_text(encoding="utf-8")
    assert "revoke insert, update, delete on public.orders" in financial
    assert "revoke insert, update, delete on public.payments" in financial
    assert "security definer" in financial
    assert "storage.objects.name" in storage
