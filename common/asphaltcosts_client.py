"""AsphaltCosts shared calculation engine client.

The website (https://asphaltcosts.com/) remains the deterministic calculation
layer. The desktop system must call the shared calculation engine whenever a
deterministic asphalt quantity or cost calculation is already supported by the
web product — the desktop never reimplements the formula as a separate tool.

This client:

  1. if a documented API endpoint is configured, POSTs the inputs and uses the
     engine response;
  2. otherwise uses the *documented* web-engine math as a local mirror, labeled
     engine_version="asphaltcosts-web-engine/1.0-mirror", so results stay
     reproducible offline while remaining traceable to the web engine.

Engine math (as documented on the site, "How this was calculated"):

    compacted_volume_ft3 = area_sq_ft * thickness_in / 12
    weight_lb            = compacted_volume_ft3 * density_pcf
    net_tons             = weight_lb / 2000
    order_tons           = net_tons * (1 + allowance)
    truckloads           = ceil(order_tons / truck_capacity_tons)
    material_cost        = order_tons * price_per_ton   (material-only basis)
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Optional

from .config import get as cfg_get
from .errors import APIError, CalculationValidationFailure

ENGINE_VERSION_MIRROR = "asphaltcosts-web-engine/1.0-mirror"


class AsphaltCostsClient:
    def __init__(
        self,
        config: dict,
        *,
        base_url: str | None = None,
        endpoint: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
        fallback_to_mirror: bool | None = None,
    ):
        self.config = config
        self.base_url = (base_url or cfg_get(config, "asphaltcosts.base_url")).rstrip("/")
        self.endpoint = endpoint or cfg_get(config, "asphaltcosts.api_endpoint")
        self.api_key = api_key or cfg_get(config, "asphaltcosts.api_key_env")
        self.timeout = timeout or cfg_get(config, "asphaltcosts.timeout_seconds", 20)
        self.fallback_to_mirror = (
            fallback_to_mirror
            if fallback_to_mirror is not None
            else cfg_get(config, "asphaltcosts.fallback_to_mirror", True)
        )
        self.engine_version = ENGINE_VERSION_MIRROR
        self.calc_runs: list[dict] = []

    # -- public API ---------------------------------------------------------

    def calculate_quantity(
        self,
        area_sq_ft: float,
        thickness_in: float,
        density_pcf: float = 145.0,
        order_allowance: float = 0.05,
        truck_capacity_tons: float = 20.0,
        price_per_ton: Optional[float] = None,
        *,
        calc_id: Optional[str] = None,
    ) -> dict:
        """Net/order tons, truckloads and (optional) material cost.

        Raises E010 when inputs fail the documented engine constraints.
        """
        if area_sq_ft <= 0 or thickness_in <= 0:
            raise CalculationValidationFailure(
                "Engine inputs invalid: area and finished thickness must be > 0."
            )
        if not (0.0 <= order_allowance <= 1.0):
            raise CalculationValidationFailure(
                f"Engine input invalid: allowance {order_allowance:.2%} outside 0-100%."
            )

        payload = {
            "area_sq_ft": area_sq_ft,
            "thickness_in": thickness_in,
            "density_pcf": density_pcf,
            "order_allowance": order_allowance,
            "truck_capacity_tons": truck_capacity_tons,
            "price_per_ton": price_per_ton,
        }

        if self.endpoint:
            try:
                result = self._post(payload)
                self.engine_version = result.get("engine_version", "asphaltcosts-web-engine/http")
                method = "http"
            except APIError as exc:
                if not self.fallback_to_mirror:
                    raise
                result = self._mirror(payload)
                method = f"mirror_after_api_error({exc.code})"
        else:
            result = self._mirror(payload)
            method = "mirror"

        result["method"] = method
        result["engine_version"] = self.engine_version
        result["calc_id"] = calc_id or f"calc-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}"
        self.calc_runs.append(result)
        return result

    def calculate_cost(self, order_tons: float, price_per_ton: float) -> dict:
        """Material-only cost per the web engine (user-supplied price)."""
        return {
            "order_tons": order_tons,
            "price_per_ton": price_per_ton,
            "material_cost": order_tons * price_per_ton,
            "cost_basis": "material_only",
            "engine_version": self.engine_version,
        }

    # -- internals ----------------------------------------------------------

    def _post(self, payload: dict) -> dict:
        import requests  # local import, optional dependency

        url = f"{self.base_url}{self.endpoint}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            raise APIError(f"Calculation engine request failed: {exc}", detail=url) from exc

    def _mirror(self, payload: dict) -> dict:
        area = float(payload["area_sq_ft"])
        thickness = float(payload["thickness_in"])
        density = float(payload["density_pcf"])
        allowance = float(payload["order_allowance"])
        capacity = float(payload["truck_capacity_tons"])
        price = payload.get("price_per_ton")

        compacted_volume = area * thickness / 12.0
        weight_lb = compacted_volume * density
        net_tons = weight_lb / 2000.0
        order_tons = net_tons * (1.0 + allowance)
        loads = math.ceil(order_tons / capacity) if capacity and capacity > 0 else None
        last_load_tons = (order_tons - (loads - 1) * capacity) if loads else None

        result = {
            "area_sq_ft": area,
            "thickness_in": thickness,
            "density_pcf": density,
            "order_allowance": allowance,
            "compacted_volume_ft3": round(compacted_volume, 6),
            "weight_lb": round(weight_lb, 3),
            "net_tons": round(net_tons, 6),
            "metric_tons": round(net_tons * 0.90718474, 6),
            "order_tons": round(order_tons, 6),
            "truck_capacity_tons": capacity,
            "truckloads": loads,
            "last_load_tons": round(last_load_tons, 6) if last_load_tons is not None else None,
            "material_cost": round(order_tons * price, 2) if price is not None else None,
            "cost_basis": "material_only" if price is not None else None,
            "steps": [
                {"step": 1, "operation": "compacted volume", "formula": "area x thickness / 12"},
                {"step": 2, "operation": "weight", "formula": "volume x density"},
                {"step": 3, "operation": "net tons", "formula": "weight / 2000"},
                {"step": 4, "operation": "order tons", "formula": "net x (1 + allowance)"},
                {"step": 5, "operation": "truckloads", "formula": "ceil(order / capacity)"},
            ],
        }
        return result
