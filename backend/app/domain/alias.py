import secrets
import string

ALIAS_LENGTH = 6
_ALPHABET = string.ascii_letters + string.digits


def generate_alias() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(ALIAS_LENGTH))
