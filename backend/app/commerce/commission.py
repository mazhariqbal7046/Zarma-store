from decimal import Decimal, ROUND_HALF_UP


# Current platform policy: retain 10% of the final eligible selling price.
# The database trigger is updated by the matching Supabase migration.
COMMISSION_RATE = Decimal("0.10")


def calculate_commission(eligible_selling_price_pkr: int) -> tuple[int, int]:
    """Return (platform commission, seller earnings) in whole PKR.

    The caller must pass the final eligible selling price after applying the
    explicitly defined discount basis. Never calculate this from client input.
    """
    if eligible_selling_price_pkr < 0:
        raise ValueError("eligible selling price cannot be negative")
    commission = (Decimal(eligible_selling_price_pkr) * COMMISSION_RATE).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(commission), eligible_selling_price_pkr - int(commission)
