from app.domain.alias import ALIAS_LENGTH, generate_alias


def test_alias_is_six_letters_or_digits():
    aliases = {generate_alias() for _ in range(50)}
    assert ALIAS_LENGTH == 6
    assert all(len(a) == 6 and a.isascii() and a.isalnum() for a in aliases)
    assert len(aliases) > 1
