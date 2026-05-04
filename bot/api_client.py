"""
Async REST API client for Molty Royale.
All endpoints from api-summary.md with rate limiting and error handling.
"""

import json
import httpx
from typing import Optional
from bot.config import API_BASE, SKILL_VERSION
from bot.utils.logger import get_logger
from bot.utils.rate_limiter import rest_limiter

log = get_logger(__name__)


class APIError(Exception):
    def __init__(self, code: str, message: str, status: int = 0):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(f"[{code}] {message}")


class MoltyAPI:
    """Async HTTP client for all Molty Royale REST endpoints."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self):
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=API_BASE,
                timeout=httpx.Timeout(30.0, connect=10.0),
            )

    def _headers(self) -> dict:
        h = {
            "X-Version": SKILL_VERSION,
            "Content-Type": "application/json",
        }
        if self.api_key:
            h["X-API-Key"] = self.api_key
        return h

    def _safe_parse_json(self, text: str) -> dict:
        """Parse JSON safely, handling malformed/concatenated responses."""
        text = text.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            decoder = json.JSONDecoder()
            try:
                obj, _ = decoder.raw_decode(text)
                log.debug("Parsed partial JSON (extra data ignored)")
                return obj
            except json.JSONDecodeError as e:
                log.warning("Unparseable API response: %s... err=%s", text[:120], e)
                return {}

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Rate-limited request with error handling."""
        await rest_limiter.acquire()
        await self._ensure_client()

        # ✅ FIX: selalu kirim header setiap request
        resp = await self._client.request(
            method,
            path,
            headers=self._headers(),
            **kwargs
        )

        # Handle version mismatch
        if resp.status_code == 426:
            raise APIError("VERSION_MISMATCH", "Skill version outdated", 426)

        # Handle rate limiting
        if resp.status_code == 429:
            log.warning("Rate limited (429). Backing off.")
            raise APIError("RATE_LIMITED", "Too many requests", 429)

        data = self._safe_parse_json(resp.text)

        # ✅ DEBUG LOG (PENTING)
        log.info("API %s %s → %s | response=%s", method, path, resp.status_code, data)

        # Check for error response shape
        if isinstance(data, dict) and not data.get("success", True) and "error" in data:
            err = data["error"]
            raise APIError(
                err.get("code", "UNKNOWN") if isinstance(err, dict) else "UNKNOWN",
                err.get("message", "Unknown error") if isinstance(err, dict) else str(err),
                resp.status_code,
            )

        # Extract data field
        if isinstance(data, dict):
            result = data.get("data", data)
            if not isinstance(result, dict):
                return {"value": result, "_raw": data}
            return result

        return {"_raw": data}

    # ── Account endpoints ─────────────────────────────────────────────

    async def create_account(self, name: str, wallet_address: str) -> dict:
        log.info("Creating account: name=%s wallet=%s", name, wallet_address[:10] + "...")
        return await self._request("POST", "/accounts", json={
            "name": name,
            "wallet_address": wallet_address,
        })

    async def get_accounts_me(self) -> dict:
        return await self._request("GET", "/accounts/me")

    async def put_wallet(self, wallet_address: str) -> dict:
        return await self._request("PUT", "/accounts/wallet", json={
            "wallet_address": wallet_address,
        })

    # ── Wallet & whitelist ────────────────────────────────────────────

    async def create_wallet(self, owner_eoa: str) -> dict:
        log.info("Creating MoltyRoyale Wallet for owner=%s", owner_eoa[:10] + "...")
        return await self._request("POST", "/create/wallet", json={
            "ownerEoa": owner_eoa,
        })

    async def whitelist_request(self, owner_eoa: str) -> dict:
        log.info("Requesting whitelist for owner=%s", owner_eoa[:10] + "...")
        return await self._request("POST", "/whitelist/request", json={
            "ownerEoa": owner_eoa,
        })

    # ── Identity ──────────────────────────────────────────────────────

    async def post_identity(self, agent_id: int) -> dict:
        log.info("Registering identity: agentId=%s", agent_id)

        if not isinstance(agent_id, int):
            log.error("agentId HARUS integer! Dapat: %s", agent_id)
            return {}

        return await self._request("POST", "/identity", json={
            "agentId": agent_id,
        })

    async def get_identity(self) -> dict:
        return await self._request("GET", "/identity")

    async def delete_identity(self) -> dict:
        log.info("Unregistering current identity")
        return await self._request("DELETE", "/identity")

    # ── Free matchmaking ──────────────────────────────────────────────

    async def post_join(self, entry_type: str = "free") -> dict:
        log.debug("Joining queue: entryType=%s", entry_type)

        await self._ensure_client()
        await rest_limiter.acquire()

        resp = await self._client.post(
            "/join",
            json={"entryType": entry_type},
            headers=self._headers(),
            timeout=httpx.Timeout(20.0),
        )

        if resp.status_code == 426:
            raise APIError("VERSION_MISMATCH", "Skill version outdated", 426)

        if resp.status_code == 429:
            raise APIError("RATE_LIMITED", "Too many requests", 429)

        data = self._safe_parse_json(resp.text)

        log.info("API POST /join → %s | response=%s", resp.status_code, data)

        if isinstance(data, dict) and not data.get("success", True) and "error" in data:
            err = data["error"]
            raise APIError(
                err.get("code", "UNKNOWN") if isinstance(err, dict) else "UNKNOWN",
                err.get("message", "Unknown error") if isinstance(err, dict) else str(err),
                resp.status_code,
            )

        if isinstance(data, dict) and "data" in data:
            result = data["data"]
            return result if isinstance(result, dict) else {"value": result, "_raw": data}

        return data if isinstance(data, dict) else {"_raw": data}

    async def get_join_status(self) -> dict:
        return await self._request("GET", "/join/status")

    # ── Paid join ─────────────────────────────────────────────────────

    async def get_games(self, status: str = "waiting") -> dict:
        return await self._request("GET", "/games", params={"status": status})

    async def get_join_paid_message(self, game_id: str) -> dict:
        return await self._request("GET", f"/games/{game_id}/join-paid/message")

    async def post_join_paid(self, game_id: str, deadline: str,
                             signature: str, mode: str = "offchain") -> dict:
        body = {"deadline": deadline, "signature": signature}
        if mode == "onchain":
            body["mode"] = "onchain"
        return await self._request("POST", f"/games/{game_id}/join-paid", json=body)

    # ── Version ───────────────────────────────────────────────────────

    async def get_version(self) -> dict:
        return await self._request("GET", "/version")

    # ── Cleanup ───────────────────────────────────────────────────────

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
