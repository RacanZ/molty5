"""
Free game join via matchmaking queue.
POST /join (Long Poll ~15s) → assigned → open WS immediately.
Compatible with servers WITHOUT /join/status endpoint.
"""

import asyncio
from bot.api_client import MoltyAPI, APIError
from bot.utils.logger import get_logger

log = get_logger(__name__)


async def join_free_game(api: MoltyAPI) -> tuple[str, str]:
    """
    Enter free matchmaking queue and wait for assignment.
    Returns (game_id, agent_id) when assigned.
    """

    attempt = 0

    while True:
        attempt += 1
        log.info("Free queue attempt #%d...", attempt)

        try:
            resp = await api.post_join("free")

            # Safety check
            if not isinstance(resp, dict):
                log.warning("Unexpected join response type: %s", type(resp).__name__)
                await asyncio.sleep(1)
                continue

            status = resp.get("status", "")

            # ✅ SUCCESS CASE
            if status == "assigned":
                game_id = resp.get("gameId", "")
                agent_id = resp.get("agentId", "")

                if game_id and agent_id:
                    log.info("✅ Assigned to free game: %s (agent=%s)", game_id, agent_id)
                    return game_id, agent_id

                log.warning("Assigned but missing IDs: %s", resp)
                await asyncio.sleep(1)
                continue

            # ⏳ STILL QUEUING
            if status in ("queued", "not_selected", ""):
                log.debug("Queue status: %s — waiting...", status)
                continue

            # ⚠️ UNKNOWN RESPONSE
            log.warning("Unexpected queue response: %s", resp)
            await asyncio.sleep(1)

        except APIError as e:
            # ❌ HARD ERRORS (STOP)
            if e.code == "NO_IDENTITY":
                log.error("❌ ERC-8004 identity belum terdaftar.")
                raise

            if e.code == "OWNERSHIP_LOST":
                log.error("❌ NFT identity berubah / hilang.")
                raise

            if e.code == "TOO_MANY_AGENTS_PER_IP":
                log.error("❌ Terlalu banyak agent dari IP ini.")
                raise

            if e.code == "ACCOUNT_ALREADY_IN_GAME":
                log.info("Akun sudah ada di game. Kembali ke heartbeat.")
                raise

            # ⚠️ SOFT ERROR (RETRY)
            log.warning("Join error: %s — retrying...", e)
            await asyncio.sleep(2)

        except Exception as e:
            # ❗ UNKNOWN ERROR
            log.error("Unexpected error: %s", e)
            await asyncio.sleep(2)