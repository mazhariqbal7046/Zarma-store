import asyncio

from app import ai_assistant


def _catalog() -> list[dict]:
    return [
        {
            "id": "shirt-1",
            "name": "Black Oxford Shirt",
            "description": "Men's cotton shirt",
            "price_pkr": 2500,
            "active": True,
            "product_variants": [
                {"id": "v1", "size": "M", "color": "Black", "price_pkr": 2500, "inventory": {"quantity": 4, "reserved_quantity": 1}}
            ],
        },
        {
            "id": "trouser-1",
            "name": "Black Chino Trouser",
            "description": "Slim trouser",
            "price_pkr": 2800,
            "active": True,
            "product_variants": [{"id": "v2", "size": "M", "color": "Black", "price_pkr": 2800, "inventory": {"quantity": 2, "reserved_quantity": 0}}],
        },
        {
            "id": "shoe-1",
            "name": "White Running Shoes",
            "description": "Running footwear",
            "price_pkr": 4500,
            "active": True,
            "product_variants": [{"id": "v3", "size": "42", "color": "White", "price_pkr": 4500, "inventory": {"quantity": 1, "reserved_quantity": 0}}],
        },
        {
            "id": "shirt-2",
            "name": "Red Shirt",
            "description": "Casual shirt",
            "price_pkr": 1800,
            "active": True,
            "product_variants": [{"id": "v4", "size": "M", "color": "Red", "price_pkr": 1800, "inventory": {"quantity": 0, "reserved_quantity": 0}}],
        },
    ]


def test_search_intent_extracts_color_category_budget_and_size() -> None:
    intent = ai_assistant.parse_search_intent("Black shirt size M under 3000 rupees")
    assert intent.colors == ("black",)
    assert "shirt" in intent.category_terms
    assert intent.sizes == ("m",)
    assert intent.max_price_pkr == 3000


def test_catalog_filter_uses_only_real_records() -> None:
    intent = ai_assistant.parse_search_intent("black shirt under 3000 in stock")
    products = ai_assistant.filter_catalog(_catalog(), intent)
    assert [product["id"] for product in products] == ["shirt-1"]


def test_outfit_recommendations_are_catalog_records() -> None:
    intent = ai_assistant.parse_search_intent("black shirt")
    products = ai_assistant.outfit_recommendations(_catalog(), intent)
    ids = {product["id"] for product in products}
    assert {"shirt-1", "trouser-1"}.issubset(ids)
    assert "made-up-product" not in ids


def test_fallback_contains_only_supplied_product_facts() -> None:
    reply = ai_assistant.fallback_reply("black shirt", [_catalog()[0]])
    assert "Black Oxford Shirt" in reply
    assert "2500" in reply
    assert "made-up-product" not in reply


def test_gemini_unavailable_uses_catalog_fallback(monkeypatch) -> None:
    monkeypatch.setattr(ai_assistant, "genai", None)
    reply, fallback = asyncio.run(ai_assistant.grounded_assistant_reply("black shirt", [_catalog()[0]]))
    assert fallback is True
    assert "Black Oxford Shirt" in reply
