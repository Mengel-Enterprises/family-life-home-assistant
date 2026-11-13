"""Shared entity base: one device per family."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FamilyLifeCoordinator


class FamilyLifeEntity(CoordinatorEntity[FamilyLifeCoordinator]):
    """Base for Family Life entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FamilyLifeCoordinator, key: str) -> None:
        """key is unique within the family."""
        super().__init__(coordinator)
        family = coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        self._attr_unique_id = f"{family}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, family)},
            name="Family Life",
            manufacturer="Family Life",
            entry_type=DeviceEntryType.SERVICE,
        )
