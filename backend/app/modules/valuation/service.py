from decimal import Decimal


def discounted_cash_flow(
    cash_flows: list[Decimal], discount_rate: Decimal, terminal_value: Decimal = Decimal("0")
) -> Decimal:
    if discount_rate <= Decimal("-1"):
        raise ValueError("discount_rate must be greater than -1")
    present_value = sum(
        (cash_flow / ((Decimal("1") + discount_rate) ** year))
        for year, cash_flow in enumerate(cash_flows, start=1)
    )
    if cash_flows:
        present_value += terminal_value / ((Decimal("1") + discount_rate) ** len(cash_flows))
    return present_value.quantize(Decimal("0.01"))

