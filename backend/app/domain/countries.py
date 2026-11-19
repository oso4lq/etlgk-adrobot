import unicodedata
from dataclasses import dataclass
from functools import cache

import pycountry


@dataclass(frozen=True)
class Country:
    code: str
    name: str


def _sort_key(country: Country) -> str:
    # Plain code-point order puts "Åland Islands" after "Zimbabwe". NFKD splits the letter from its
    # accent, and dropping the accent leaves "aland islands", which sorts next to "Albania".
    decomposed = unicodedata.normalize("NFKD", country.name).casefold()
    return "".join(char for char in decomposed if not unicodedata.combining(char))


@cache
def _sorted_countries() -> tuple[Country, ...]:
    # ISO `name` is used even where pycountry has `common_name`: it is stable and matches ISO.
    countries = [Country(code=item.alpha_2, name=item.name) for item in pycountry.countries]
    return tuple(sorted(countries, key=_sort_key))


def list_countries() -> list[Country]:
    # A new list each time: callers may mutate it, the cached data must stay intact.
    return list(_sorted_countries())


@cache
def _countries_by_code() -> dict[str, Country]:
    return {country.code: country for country in _sorted_countries()}


def find_country(code: str) -> Country | None:
    return _countries_by_code().get(code.strip().upper())
