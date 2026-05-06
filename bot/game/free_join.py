import asyncio
from bot.api_client import MoltyAPI, APIError
from bot.utils.logger import get_logger

log = get_logger(__name__)


async def join_free_game(api: MoltyAPI) -> tuple[str, str]:
    """
    Join free matchmaking queue (official API).
    FIXED:
    - no /join/status
    - anti spam
    - stabil loop
    """

    attempt = 0
    wait_time = 2  # mulai dari 2 detik

    while True:
        attempt += 1
        log.info("Free queue attempt #%d...", attempt)

        try:
            resp = await api.post_join("free")

            log.info("JOIN RESPONSE: %s", resp)

            if not isinstance(resp, dict):
                await asyncio.sleep(wait_time)
                continue

            status = resp.get("status")

            # ✅ MASUK GAME
            if status == "assigned":
                game_id = resp.get("gameId")
                agent_id = resp.get("agentId")

                if game_id and agent_id:
                    log.info("✅ MATCHED → %s | agent=%s", game_id, agent_id)
                    return game_id, agent_id

            # ⏳ MASIH MATCHMAKING
            if status in ("queued", "not_selected", None):
                log.info("Status: %s | waiting...", status)

                # naikkan delay perlahan (anti spam)
                wait_time = min(wait_time + 1, 10)
                await asyncio.sleep(wait_time)
                continue

            # ⚠️ RESPONSE ANEH
            log.warning("Unknown response: %s", resp)
            await asyncio.sleep(wait_time)

        except APIError as e:

            if e.code == "NO_IDENTITY":
                log.error("❌ Identity belum ada")
                raise

            if e.code == "TOO_MANY_AGENTS_PER_IP":
                log.error("❌ IP limit kena")
                raise

            log.warning("API Error: %s", e)
            await asyncio.sleep(5)

        except Exception as e:
            log.error("Unexpected error: %s", e)
            await asyncio.sleep(5)