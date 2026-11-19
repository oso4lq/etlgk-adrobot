from app.domain.countries import Country, find_country, list_countries


def test_countries_are_iso_alpha2_sorted_by_name():
    countries = list_countries()
    assert len(countries) >= 249
    assert all(len(c.code) == 2 and c.code.isupper() for c in countries)
    assert [c.name for c in countries] == sorted(c.name for c in countries)


def test_find_country_ignores_case_and_spaces():
    assert find_country(" de ") == Country("DE", "Germany")
    assert find_country("XX") is None
