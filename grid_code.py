"""Apply SMA grid code presets via Modbus writes."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Union

from sma_modbus import SMAModbusClient

logger = logging.getLogger(__name__)


def load_grid_presets(path: Union[str, Path]) -> Dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data


def resolve_grid_code(grid_code: str, presets: Dict) -> Optional[Dict[str, Union[int, float]]]:
    """Resolve preset name or numeric country code into write values."""
    code = grid_code.strip()
    if not code or code.lower() in ("none", "off", "skip"):
        return None

    preset_map = presets.get("presets", {})
    if code in preset_map:
        return dict(preset_map[code])

    if code.isdigit():
        return {"country_code": int(code)}

    upper = code.upper()
    if upper in preset_map:
        return dict(preset_map[upper])

    logger.error("Unknown grid code preset: %s", grid_code)
    return None


def apply_grid_code(
    client: SMAModbusClient,
    grid_code: str,
    presets_path: Union[str, Path],
    extra_writes: Optional[Dict[str, Union[int, float]]] = None,
) -> Dict[str, bool]:
    """Write grid code and related RW grid parameters to the inverter."""
    presets = load_grid_presets(presets_path)
    values = resolve_grid_code(grid_code, presets)
    if not values:
        return {}

    mapping = presets.get("register_mapping", {})
    writes: Dict[str, Union[int, float]] = {}

    for preset_key, register_name in mapping.items():
        if preset_key in values:
            writes[register_name] = values[preset_key]

    if extra_writes:
        writes.update(extra_writes)

    logger.info("Applying grid code %s with writes: %s", grid_code, writes)
    return client.write_many(writes)
