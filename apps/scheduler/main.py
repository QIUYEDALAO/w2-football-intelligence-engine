from __future__ import annotations

import logging

logger = logging.getLogger("w2.scheduler")


def heartbeat() -> str:
    message = "w2 scheduler heartbeat"
    logger.info(message)
    return message


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    heartbeat()

