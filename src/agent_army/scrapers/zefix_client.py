"""ZEFIX REST API Client for Swiss company registry."""

from __future__ import annotations

from typing import Any, Optional

import httpx
from loguru import logger


class ZefixClient:
    """
    Client for the Swiss ZEFIX (Zentraler Firmenindex) REST API.

    API: https://www.zefix.ch/ZefixREST/api/v1
    Provides access to the Swiss commercial register.
    """

    BASE_URL = "https://www.zefix.ch/ZefixREST/api/v1"

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._logger = logger.bind(component="ZefixClient")

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Accept": "application/json",
                "User-Agent": "AgentArmy/0.2.0",
            },
        )

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()

    async def search_companies(
        self,
        name: str,
        canton: Optional[str] = None,
        legal_form: Optional[str] = None,
        active_only: bool = True,
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Search for companies in the Swiss commercial register.

        Args:
            name: Company name to search for
            canton: Canton code (e.g., "ZH", "BE", "BS")
            legal_form: Legal form filter (e.g., "AG", "GmbH")
            active_only: Only return active companies
            max_results: Maximum results to return

        Returns:
            List of company records
        """
        if not self._client:
            return []

        params: dict[str, Any] = {
            "name": name,
            "maxEntries": max_results,
        }
        if canton:
            params["registryOfficeId"] = self._canton_to_registry(canton)
        if active_only:
            params["activeOnly"] = "true"

        try:
            response = await self._client.get(
                f"{self.BASE_URL}/company/search",
                params=params,
            )

            if response.status_code == 200:
                data = response.json()
                companies = data if isinstance(data, list) else data.get("list", [])
                self._logger.debug(f"ZEFIX search '{name}': {len(companies)} results")
                return [self._normalize_company(c) for c in companies[:max_results]]
            else:
                self._logger.warning(f"ZEFIX search failed: {response.status_code}")
                return []

        except Exception as e:
            self._logger.warning(f"ZEFIX search error: {e}")
            return []

    async def get_company(self, uid: str) -> Optional[dict[str, Any]]:
        """
        Get detailed company info by UID.

        Args:
            uid: Swiss company UID (e.g., "CHE-123.456.789")

        Returns:
            Company details or None
        """
        if not self._client:
            return None

        uid_clean = uid.replace(".", "").replace("-", "")

        try:
            response = await self._client.get(f"{self.BASE_URL}/company/uid/{uid_clean}")

            if response.status_code == 200:
                return self._normalize_company(response.json())
            return None

        except Exception as e:
            self._logger.warning(f"ZEFIX get error: {e}")
            return None

    def _normalize_company(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize ZEFIX API response to our schema."""
        return {
            "name": raw.get("name", ""),
            "uid": raw.get("uid", ""),
            "chid": raw.get("chid", ""),
            "legal_form": raw.get("legalForm", {}).get("name", {}).get("de", ""),
            "status": raw.get("status", ""),
            "canton": raw.get("canton", ""),
            "municipality": raw.get("legalSeat", ""),
            "address": self._extract_address(raw),
            "purpose": raw.get("purpose", {}).get("de", ""),
            "registration_date": raw.get("registrationDate", ""),
        }

    def _extract_address(self, raw: dict[str, Any]) -> str:
        """Extract address from ZEFIX data."""
        address = raw.get("address", {})
        if isinstance(address, dict):
            parts = [
                address.get("street", ""),
                address.get("houseNumber", ""),
                address.get("swissZipCode", ""),
                address.get("city", ""),
            ]
            return " ".join(p for p in parts if p)
        return ""

    def _canton_to_registry(self, canton: str) -> Optional[str]:
        """Map canton abbreviation to registry office ID."""
        canton_map = {
            "ZH": "100",
            "BE": "110",
            "LU": "120",
            "UR": "130",
            "SZ": "140",
            "OW": "150",
            "NW": "160",
            "GL": "170",
            "ZG": "180",
            "FR": "190",
            "SO": "200",
            "BS": "210",
            "BL": "220",
            "SH": "230",
            "AR": "240",
            "AI": "250",
            "SG": "260",
            "GR": "270",
            "AG": "280",
            "TG": "290",
            "TI": "300",
            "VD": "310",
            "VS": "320",
            "NE": "330",
            "GE": "340",
            "JU": "350",
        }
        return canton_map.get(canton.upper())
