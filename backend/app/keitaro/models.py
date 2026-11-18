from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

# Keitaro returns many more fields than we use; unknown ones are dropped on purpose so that
# the rest of the app depends only on what it needs.
_MODEL_CONFIG = ConfigDict(extra="ignore", populate_by_name=True)


class KeitaroOffer(BaseModel):
    model_config = _MODEL_CONFIG

    id: int
    name: str
    state: str


class KeitaroDomain(BaseModel):
    model_config = _MODEL_CONFIG

    id: int
    name: str
    state: str


class KeitaroGroup(BaseModel):
    model_config = _MODEL_CONFIG

    id: int
    name: str
    type: str


class KeitaroTrafficSource(BaseModel):
    model_config = _MODEL_CONFIG

    id: int
    name: str
    state: str


class KeitaroCampaign(BaseModel):
    model_config = _MODEL_CONFIG

    id: int
    name: str
    alias: str
    type: str
    state: str
    domain: str | None = None
    domain_id: int | None = None
    group_id: int | None = None
    traffic_source_id: int | None = None


class KeitaroStreamOffer(BaseModel):
    model_config = _MODEL_CONFIG

    offer_id: int
    share: int
    state: str


class KeitaroStream(BaseModel):
    model_config = _MODEL_CONFIG

    id: int
    campaign_id: int
    name: str
    type: str
    position: int
    state: str
    # `schema` shadows a BaseModel attribute, hence the alias.
    flow_schema: str = Field(alias="schema")
    action_type: str | None = None
    offers: list[KeitaroStreamOffer] = Field(default_factory=list)


@dataclass(frozen=True)
class StreamOfferShare:
    offer_id: int
    share: int


@dataclass(frozen=True)
class NewCampaign:
    name: str
    alias: str
    domain_id: int
    group_id: int
    traffic_source_id: int


@dataclass(frozen=True)
class NewCountryRedirectStream:
    campaign_id: int
    name: str
    position: int
    country_code: str
    redirect_url: str


@dataclass(frozen=True)
class NewOffersStream:
    campaign_id: int
    name: str
    position: int
    offers: tuple[StreamOfferShare, ...]
