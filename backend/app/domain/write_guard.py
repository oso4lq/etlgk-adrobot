"""Protection of the shared Keitaro: writes are allowed only to campaigns with our name prefix."""


def is_write_allowed(campaign_name: str, prefix: str) -> bool:
    return not prefix or campaign_name.startswith(prefix)


def write_forbidden_message(prefix: str) -> str:
    return f"Публикация запрещена: название кампании не начинается с «{prefix}»"
