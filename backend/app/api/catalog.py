from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_offer_catalog
from app.domain.countries import list_countries
from app.schemas.catalog import CountryResponse, OfferResponse
from app.services.offer_catalog import OfferCatalog

router = APIRouter(prefix="/api")


@router.get("/offers", response_model=list[OfferResponse])
def search_offers(
    catalog: Annotated[OfferCatalog, Depends(get_offer_catalog)], query: str = ""
) -> list[OfferResponse]:
    return [OfferResponse(id=offer.id, name=offer.name) for offer in catalog.search(query)]


@router.get("/countries", response_model=list[CountryResponse])
def get_countries() -> list[CountryResponse]:
    return [CountryResponse(code=item.code, name=item.name) for item in list_countries()]
