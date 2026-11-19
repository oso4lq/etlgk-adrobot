from app.domain.countries import Country, find_country, list_countries


def test_countries_are_iso_alpha2_sorted_by_name():
    countries = list_countries()
    assert len(countries) >= 249
    assert all(len(c.code) == 2 and c.code.isupper() for c in countries)
    assert [c.name for c in countries[:3]] == ["Afghanistan", "Åland Islands", "Albania"]


def test_find_country_ignores_case_and_spaces():
    assert find_country(" de ") == Country("DE", "Germany")
    assert find_country("XX") is None


def test_accented_names_sort_by_their_base_letters():
    names = [country.name for country in list_countries()]
    assert names.index("Åland Islands") < names.index("Albania")


def test_returned_list_can_be_mutated_without_side_effects():
    first = list_countries()
    first.clear()
    assert len(list_countries()) >= 249
