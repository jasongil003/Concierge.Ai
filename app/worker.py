"""Dedicated durable background worker process for production deployments."""

from __future__ import annotations

import asyncio
import logging

from .main import app, settings


async def run() -> None:
    if not settings.background_workers_enabled:
        raise RuntimeError("ENABLE_BACKGROUND_WORKERS must be enabled for the worker process.")
    async with app.router.lifespan_context(app):
        await asyncio.Event().wait()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
