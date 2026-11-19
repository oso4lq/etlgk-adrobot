from pydantic import BaseModel


class OfferResponse(BaseModel):
    id: int
    name: str


class CountryResponse(BaseModel):
    code: str
    name: str
