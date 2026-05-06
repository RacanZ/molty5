"""
Free game join via matchmaking queue.
- Compatible with server WITHOUT /join/status
- Anti spam (delay adaptif)
- Debug lengkap untuk deteksi suspend / shadow block
"""

import asyncio
from bot.api_client import MoltyAPI, APIError
from bot.utils.logger import get_logger

log = get_logger(__name__)


async def join_free_game(api: MoltyAPI) -> tuple[str, str]:
    """
    Join free matchmaking queue (long polling).
    Return (game_id, agent_id) jika berhasil.
    """

    attempt = 0
    last_status = None

    while True:
        attempt += 1
        log.info("Free queue attempt #%d...", attempt)

        try:
            resp = await api.post_join("free")

            # 🔍 DEBUG WAJIB
            log.info("JOIN RESPONSE: %s", resp)

            # Safety check
            if not isinstance(resp, dict):
                log.warning("Response bukan dict: %s", type(resp).__name__)
                await asyncio.sleep(2)
                continue

            status = resp.get("status", "")

            # ✅ BERHASIL MASUK GAME
            if status == "assigned":
                game_id = resp.get("gameId")
                agent_id = resp.get("agentId")

                if game_id and agent_id:
                    log.info("✅ MASUK GAME: %s | agent=%s", game_id, agent_id)
                    return game_id, agent_id

                log.warning("Assigned tapi data tidak lengkap: %s", resp)
                await asyncio.sleep(2)
                continue

            # ⏳ MASIH QUEUE
            if status in ("queued", "not_selected", ""):
                if status != last_status:
                    log.info("Status queue: %s", status)
                    last_status = status

                # ⛔ DETEKSI SHADOW BLOCK
                if attempt > 20:
                    log.warning("⚠️ Sudah >20x belum masuk game")
                    log.warning("Kemungkinan:")
                    log.warning("1. Server sepi")
                    log.warning("2. Akun kena limit / shadow block")
                    log.warning("3. API key tidak eligible")

                # delay biar tidak dianggap spam
                await asyncio.sleep(2)
                continue

            # ⚠️ RESPONSE ANEH
            log.warning("Response tidak dikenal: %s", resp)
            await asyncio.sleep(2)

        except APIError as e:

            # ❌ ERROR KRITIS
            if e.code == "NO_IDENTITY":
                log.error("❌ Identity belum ada (ERC-8004)")
                raise

            if e.code == "OWNERSHIP_LOST":
                log.error("❌ NFT identity tidak valid / berubah")
                raise

            if e.code == "TOO_MANY_AGENTS_PER_IP":
                log.error("❌ Terlalu banyak bot di IP ini → kemungkinan suspend")
                raise

            if e.code == "ACCOUNT_ALREADY_IN_GAME":
                log.info("Akun sudah di game → kembali ke heartbeat")
                raise

            # ⚠️ ERROR NON-FATAL
            log.warning("API Error: %s", e)
            await asyncio.sleep(3)

        except Exception as e:
            log.error("Unexpected error: %s", e)
            await asyncio.sleep(3)