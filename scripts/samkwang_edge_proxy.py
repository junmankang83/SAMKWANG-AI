#!/usr/bin/env python3
"""
8080: frontend 정적 파일 + /api·/docs·/health → 127.0.0.1:8000 프록시
"""

from __future__ import annotations

import argparse
from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import Route

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
BACKEND = "http://127.0.0.1:8000"

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _should_proxy(path: str) -> bool:
    return (
        path.startswith("/api")
        or path.startswith("/docs")
        or path.startswith("/openapi.json")
        or path.startswith("/redoc")
        or path == "/health"
    )


async def proxy_to_backend(request: Request) -> Response:
    path = request.url.path
    if not path.startswith("/"):
        path = "/" + path
    qs = request.url.query
    url = f"{BACKEND}{path}"
    if qs:
        url = f"{url}?{qs}"

    headers = [
        (k.decode("latin1"), v.decode("latin1"))
        for k, v in request.scope.get("headers", [])
        if k.decode("latin1").lower() not in HOP_BY_HOP
        and k.decode("latin1").lower() != "host"
    ]
    hdr = httpx.Headers(headers)
    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
            br = await client.request(
                request.method,
                url,
                headers=hdr,
                content=body if body else None,
            )
    except httpx.RequestError as exc:
        return Response(
            f"백엔드 연결 실패: {exc}".encode("utf-8"),
            status_code=502,
            media_type="text/plain; charset=utf-8",
        )

    out = {
        k: v
        for k, v in br.headers.items()
        if k.lower() not in HOP_BY_HOP and k.lower() != "content-length"
    }
    return Response(
        content=br.content,
        status_code=br.status_code,
        headers=out,
    )


async def static_or_spa(request: Request) -> FileResponse | Response:
    if request.method != "GET":
        raise HTTPException(status_code=405)

    rel = request.url.path.lstrip("/") or "index.html"
    if ".." in Path(rel).parts:
        raise HTTPException(status_code=403)

    target = (FRONTEND / rel).resolve()
    try:
        target.relative_to(FRONTEND.resolve())
    except ValueError:
        raise HTTPException(status_code=403) from None

    no_cache_html = {"Cache-Control": "no-store, max-age=0, must-revalidate"}

    if target.is_file():
        if target.suffix.lower() in (".html", ".htm"):
            return FileResponse(target, headers=no_cache_html)
        return FileResponse(target)

    idx = FRONTEND / "index.html"
    if idx.is_file():
        return FileResponse(idx, headers=no_cache_html)

    raise HTTPException(status_code=404, detail="frontend not found")


async def dispatch(request: Request) -> Response:
    if _should_proxy(request.url.path):
        return await proxy_to_backend(request)
    return await static_or_spa(request)


_METHODS = ["GET", "POST", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"]

app = Starlette(
    routes=[
        Route("/", dispatch, methods=_METHODS),
        Route("/{full_path:path}", dispatch, methods=_METHODS),
    ],
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", default="0.0.0.0:8080")
    a = parser.parse_args()
    host, _, port_s = a.listen.partition(":")
    port = int(port_s or "8080")
    import uvicorn

    uvicorn.run(app, host=host or "0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
