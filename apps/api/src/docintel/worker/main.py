from __future__ import annotations

import asyncio
import logging
import socket
import uuid

from docintel.core.config import get_settings
from docintel.core.logging import configure_logging
from docintel.db.session import create_engine, create_session_factory
from docintel.services.deletion import DeletionProcessor
from docintel.storage.local import LocalDocumentStorage

logger = logging.getLogger(__name__)


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    storage = LocalDocumentStorage(settings.uploads_path)
    worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:12]}"
    processor = DeletionProcessor(
        session_factory,
        storage,
        settings,
        worker_id=worker_id,
    )
    logger.info("Deletion worker started.", extra={"worker_id": worker_id})

    try:
        while True:
            processed = await processor.run_once()
            if not processed:
                await asyncio.sleep(settings.worker_poll_seconds)
    finally:
        await engine.dispose()


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
