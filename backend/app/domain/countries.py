from dataclasses import dataclass
from functools import cache

import pycountry


@dataclass(frozen=True)
class Country:
    code: str
    name: str


@cache
def list_countries() -> list[Country]:
    # ISO `name` is used even where pycountry has `common_name`: it is stable and matches ISO.
    countries = [Country(code=item.alpha_2, name=item.name) for item in pycountry.countries]
    countries.sort(key=lambda country: country.name)
    return countries


@cache
def _countries_by_code() -> dict[str, Country]:
    return {country.code: country for country in list_countries()}


def find_country(code: str) -> Country | None:
    return _countries_by_code().get(code.strip().upper())
