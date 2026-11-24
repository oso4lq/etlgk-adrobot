"""Demo stand: the real backend over an in-memory fake Keitaro, so the UI can be clicked through.

Nothing here reads `.env` or talks to a real tracker: the fake is filled like the scene from the
video, and the database is a throwaway SQLite file recreated on every start. Extra routes under
`/demo` show what the fake "Keitaro" holds and let you delete an offer there, the way a user
would in the Keitaro admin.

Run from backend/:  python -m tools.demo_stand [--port 8000]
"""

import argparse
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config
from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

from app.cli.recon import _use_utf8_output
from app.core.config import BACKEND_DIR, Settings
from app.keitaro.models import KeitaroStream
from app.main import create_app
from tests.fakes import FakeKeitaroClient

DEMO_CAMPAIGN_NAME = "test_oso4lq_demo_video"
FOREIGN_CAMPAIGN_NAME = "partner_campaign_demo"
DEMO_DATABASE_PATH = BACKEND_DIR / "demo_stand.db"


def build_demo_keitaro() -> FakeKeitaroClient:
    keitaro = FakeKeitaroClient()
    for offer_id, letter in zip(range(501, 507), "ABCDEF", strict=True):
        keitaro.add_offer(offer_id, f"Demo offer {letter}")

    demo_campaign = keitaro.add_campaign(DEMO_CAMPAIGN_NAME)
    keitaro.add_stream(demo_campaign.id, "Australia → Google", 1)
    keitaro.add_stream(demo_campaign.id, "Offers", 2, [(501, 34), (502, 33), (503, 33)])

    # Name lacks the write prefix, so pushing to it must be refused.
    foreign_campaign = keitaro.add_campaign(FOREIGN_CAMPAIGN_NAME)
    keitaro.add_stream(foreign_campaign.id, "Partner offers", 1, [(504, 100)])
    return keitaro


def demo_settings(database_url: str) -> Settings:
    # `_env_file=None` plus explicit values: neither .env nor OS variables may reach the demo.
    return Settings(
        _env_file=None,
        keitaro_base_url="https://keitaro.demo.invalid",
        keitaro_api_key="demo-stand-not-a-real-key",
        keitaro_write_name_prefix="test_oso4lq_",
        campaign_domain="kylovoa.com",
        campaign_group="FORTESTS",
        campaign_traffic_source="FORTESTS",
        database_url=database_url,
    )


def prepare_database(path: Path) -> str:
    path.unlink(missing_ok=True)
    url = f"sqlite:///{path.as_posix()}"
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")
    return url


def _stream_body(stream: KeitaroStream) -> dict:
    offers = [
        {"offer_id": offer.offer_id, "share": offer.share, "state": offer.state}
        for offer in stream.offers
    ]
    total_share = sum(offer.share for offer in stream.offers if offer.state == "active")
    return {
        "id": stream.id,
        "campaign_id": stream.campaign_id,
        "name": stream.name,
        "type": stream.type,
        "position": stream.position,
        "state": stream.state,
        "schema": stream.flow_schema,
        "action_type": stream.action_type,
        "offers": offers,
        "total_share": total_share,
    }


def _not_found(message: str) -> JSONResponse:
    return JSONResponse(status_code=404, content={"code": "demo_not_found", "message": message})


def demo_router(keitaro: FakeKeitaroClient) -> APIRouter:
    router = APIRouter(prefix="/demo")

    @router.get("/keitaro/streams/{stream_id}")
    def show_stream(stream_id: int):
        stream = keitaro.streams.get(stream_id)
        if stream is None:
            return _not_found(f"Поток {stream_id} не найден в демо-Keitaro")
        return _stream_body(stream)

    @router.post("/keitaro/streams/{stream_id}/offers/{offer_id}/delete")
    def delete_offer(stream_id: int, offer_id: int):
        stream = keitaro.streams.get(stream_id)
        if stream is None:
            return _not_found(f"Поток {stream_id} не найден в демо-Keitaro")
        remaining = []
        found = False
        for offer in stream.offers:
            if offer.offer_id == offer_id:
                found = True
            else:
                remaining.append((offer.offer_id, offer.share, offer.state))
        if not found:
            return _not_found(f"Оффера {offer_id} нет в потоке {stream_id}")
        # Shares are left as they are: a manual edit in Keitaro does not rebalance anything.
        keitaro.set_stream_offers(stream_id, remaining)
        return _stream_body(keitaro.streams[stream_id])

    return router


def build_demo_app(database_url: str) -> FastAPI:
    keitaro = build_demo_keitaro()
    app = create_app(demo_settings(database_url), keitaro_client=keitaro)
    app.include_router(demo_router(keitaro))
    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Демо-стенд Adrobot с Keitaro в памяти.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    arguments = parser.parse_args(argv)
    _use_utf8_output()

    app = build_demo_app(prepare_database(DEMO_DATABASE_PATH))
    base = f"http://{arguments.host}:{arguments.port}"
    print("Демо-стенд: настоящий Keitaro не используется, данные живут в памяти.")
    print(f"API:   {base}/api")
    print(f"Docs:  {base}/docs")
    print(f"Демо-Keitaro (поток): {base}/demo/keitaro/streams/{{id}}")
    uvicorn.run(app, host=arguments.host, port=arguments.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
