from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.core.observability import (
    REQUEST_ID_HEADER,
    http_metrics,
    install_observability,
    metrics_response,
)


def observable_app(*, metrics_enabled: bool = True, token: str | None = "metrics-secret"):
    app = FastAPI()
    install_observability(app)

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    @app.get("/metrics")
    async def metrics(request: Request):
        return metrics_response(request, metrics_enabled, token)

    return app


async def test_request_ids_are_returned_and_metrics_use_route_templates() -> None:
    http_metrics.reset()
    transport = ASGITransport(app=observable_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/items/one", headers={REQUEST_ID_HEADER: "mobile-request-1"}
        )
        assert response.status_code == 200
        assert response.headers[REQUEST_ID_HEADER] == "mobile-request-1"

        metrics = await client.get(
            "/metrics", headers={"Authorization": "Bearer metrics-secret"}
        )

    assert metrics.status_code == 200
    request_metric = (
        'relay_http_requests_total{method="GET",route="/items/{item_id}",status="200"} 1'
    )
    assert request_metric in metrics.text
    assert "item_id=one" not in metrics.text
    assert metrics.headers["Cache-Control"] == "no-store"
    http_metrics.reset()


async def test_unsafe_request_id_is_replaced() -> None:
    transport = ASGITransport(app=observable_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/items/one", headers={REQUEST_ID_HEADER: "invalid request id"}
        )

    generated = response.headers[REQUEST_ID_HEADER]
    assert generated != "invalid request id"
    assert len(generated) == 36
    http_metrics.reset()


async def test_request_id_is_exposed_to_browser_clients(client: AsyncClient) -> None:
    response = await client.get(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            REQUEST_ID_HEADER: "browser-request-1",
        },
    )

    assert response.headers[REQUEST_ID_HEADER] == "browser-request-1"
    assert REQUEST_ID_HEADER in response.headers["Access-Control-Expose-Headers"]
    http_metrics.reset()


async def test_metrics_can_be_disabled_and_require_the_bearer_token() -> None:
    disabled_transport = ASGITransport(app=observable_app(metrics_enabled=False))
    async with AsyncClient(
        transport=disabled_transport, base_url="http://test"
    ) as client:
        assert (await client.get("/metrics")).status_code == 404

    misconfigured_transport = ASGITransport(
        app=observable_app(metrics_enabled=True, token=None)
    )
    async with AsyncClient(
        transport=misconfigured_transport, base_url="http://test"
    ) as client:
        assert (await client.get("/metrics")).status_code == 503

    protected_transport = ASGITransport(app=observable_app())
    async with AsyncClient(
        transport=protected_transport, base_url="http://test"
    ) as client:
        assert (await client.get("/metrics")).status_code == 401
        assert (
            await client.get(
                "/metrics", headers={"Authorization": "Bearer metrics-secret"}
            )
        ).status_code == 200
    http_metrics.reset()
