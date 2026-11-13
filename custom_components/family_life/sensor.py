"""Sensors for automations: the next family event, chores left today per member, overdue chores."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import FamilyLifeConfigEntry
from .entity import FamilyLifeEntity
from .logic import chores_due_today, overdue_chores, parse_iso


async def async_setup_entry(hass: HomeAssistant, entry: FamilyLifeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    """Fixed sensors, plus a chores sensor per member."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([NextEventSensor(coordinator), OverdueChoresSensor(coordinator)])
    known: set[str] = set()

    @callback
    def _members() -> None:
        new = [m for m in coordinator.data.get("members", []) if m.get("id") and m["id"] not in known]
        for m in new:
            known.add(m["id"])
        if new:
            async_add_entities([ChoresTodaySensor(coordinator, m["id"], m.get("name") or "Member") for m in new])

    _members()
    entry.async_on_unload(coordinator.async_add_listener(_members))


class NextEventSensor(FamilyLifeEntity, SensorEntity):
    """When the next family event starts; its title in the attributes."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_name = "Next event"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "next_event")

    def _next(self) -> dict[str, Any] | None:
        now = dt_util.utcnow()
        for e in self.coordinator.data.get("events", []):
            start = parse_iso(e.get("startDate"))
            if start and start >= now:
                return e
        return None

    @property
    def native_value(self) -> datetime | None:
        """Start time."""
        e = self._next()
        return parse_iso(e.get("startDate")) if e else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Title and place."""
        e = self._next() or {}
        return {"title": e.get("title"), "location": e.get("location"), "all_day": e.get("allDay")}


class ChoresTodaySensor(FamilyLifeEntity, SensorEntity):
    """Open chores due today (or earlier) for one member."""

    _attr_icon = "mdi:broom"
    _attr_native_unit_of_measurement = "chores"

    def __init__(self, coordinator, member_id: str, name: str) -> None:
        """Initialize."""
        super().__init__(coordinator, f"chores_today_{member_id}")
        self._member_id = member_id
        self._attr_name = f"{name} chores today"

    @property
    def native_value(self) -> int:
        """Count."""
        return chores_due_today(self.coordinator.data, self._member_id, dt_util.now().date())


class OverdueChoresSensor(FamilyLifeEntity, SensorEntity):
    """Open chores past their due date, across the family."""

    _attr_icon = "mdi:alert-circle-outline"
    _attr_name = "Overdue chores"
    _attr_native_unit_of_measurement = "chores"

    def __init__(self, coordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "overdue_chores")

    @property
    def native_value(self) -> int:
        """Count."""
        return overdue_chores(self.coordinator.data, dt_util.now().date())
