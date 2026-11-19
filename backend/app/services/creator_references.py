from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.core.config import Settings
from app.core.errors import AppError
from app.keitaro.client import KeitaroClient
from app.keitaro.references import _HasIdAndName, find_reference


class CreatorMisconfiguredError(AppError):
    code = "creator_misconfigured"
    http_status = 503


@dataclass(frozen=True)
class CreatorReferences:
    domain_id: int
    domain_name: str
    group_id: int
    traffic_source_id: int


class CreatorReferenceResolver:
    """Turns configured domain, group and source (name or id) into Keitaro ids."""

    def __init__(self, client: KeitaroClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings
        self._resolved: CreatorReferences | None = None

    def resolve(self) -> CreatorReferences:
        # Only success is cached: a fixed config or a newly created dictionary entry must
        # be picked up without restarting the app.
        if self._resolved is not None:
            return self._resolved
        problems: list[str] = []
        domain = self._find(
            "CAMPAIGN_DOMAIN", self._settings.campaign_domain, self._client.list_domains, problems
        )
        group = self._find(
            "CAMPAIGN_GROUP",
            self._settings.campaign_group,
            self._client.list_campaign_groups,
            problems,
        )
        traffic_source = self._find(
            "CAMPAIGN_TRAFFIC_SOURCE",
            self._settings.campaign_traffic_source,
            self._client.list_traffic_sources,
            problems,
        )
        if problems or domain is None or group is None or traffic_source is None:
            raise CreatorMisconfiguredError("; ".join(problems))
        self._resolved = CreatorReferences(
            domain_id=domain.id,
            domain_name=domain.name,
            group_id=group.id,
            traffic_source_id=traffic_source.id,
        )
        return self._resolved

    @staticmethod
    def _find[T: _HasIdAndName](
        setting_name: str,
        configured: str,
        load: Callable[[], Sequence[T]],
        problems: list[str],
    ) -> T | None:
        if not configured.strip():
            problems.append(f"{setting_name} не задан")
            return None
        found = find_reference(load(), configured)
        if found is None:
            problems.append(f"{setting_name}={configured} не найден в Keitaro")
        return found
