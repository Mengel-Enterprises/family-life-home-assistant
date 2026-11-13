"""Calendars: the whole family, plus one per member."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEntityFeature, CalendarEvent
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import FamilyLifeConfigEntry
from .api import FamilyLifeError
from .entity import FamilyLifeEntity
from .logic import event_belongs_to, parse_iso


def _to_event(raw: dict[str, Any]) -> CalendarEvent | None:
    start = parse_iso(raw.get("startDate"))
    end = parse_iso(raw.get("endDate")) or start
    if start is None or end is None:
        return None
    if raw.get("allDay"):
        s: date | datetime = start.date()
        e: date | datetime = max(end.date(), start.date() + timedelta(days=1))
    else:
        s, e = start, max(end, start + timedelta(minutes=1))
    uid = raw.get("id") if raw.get("source", "app") == "app" else None
    return CalendarEvent(start=s, end=e, summary=raw.get("title") or "Event", location=raw.get("location"), uid=uid)


async def async_setup_entry(hass: HomeAssistant, entry: FamilyLifeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    """Family calendar, and a calendar per member (added as members appear)."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([FamilyLifeCalendar(coordinator, None, "Family calendar")])
    known: set[str] = set()

    @callback
    def _members() -> None:
        new = [m for m in coordinator.data.get("members", []) if m.get("id") and m["id"] not in known]
        for m in new:
            known.add(m["id"])
        if new:
            async_add_entities([FamilyLifeCalendar(coordinator, m["id"], f"{m.get('name') or 'Member'} calendar") for m in new])

    _members()
    entry.async_on_unload(coordinator.async_add_listener(_members))


class FamilyLifeCalendar(FamilyLifeEntity, CalendarEntity):
    """A Family Life calendar (whole family, or one member's)."""

    def __init__(self, coordinator, member_id: str | None, name: str) -> None:
        """member_id None = the whole family."""
        super().__init__(coordinator, f"calendar_{member_id or 'family'}")
        self._member_id = member_id
        self._attr_name = name
        if member_id is None:
            self._attr_supported_features = CalendarEntityFeature.CREATE_EVENT | CalendarEntityFeature.DELETE_EVENT

    def _mine(self, raw: dict[str, Any]) -> bool:
        return self._member_id is None or event_belongs_to(raw, self._member_id)

    @property
    def event(self) -> CalendarEvent | None:
        """The current or next event."""
        now = dt_util.now()
        for raw in self.coordinator.data.get("events", []):
            if not self._mine(raw):
                continue
            ev = _to_event(raw)
            if ev and ev.end_datetime_local >= now:
                return ev
        return None

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        """App events from the API for any range, plus connected-calendar events the board carries."""
        raws: dict[str, dict[str, Any]] = {}
        try:
            for raw in await self.coordinator.api.events(start_date, end_date):
                raws[str(raw.get("id"))] = {**raw, "source": "app", "startDate": raw.get("startDate") or raw.get("start_date"), "endDate": raw.get("endDate") or raw.get("end_date")}
        except FamilyLifeError:
            pass
        for raw in self.coordinator.data.get("events", []):
            raws.setdefault(str(raw.get("id")), raw)
        out: list[CalendarEvent] = []
        for raw in raws.values():
            if not self._mine(raw):
                continue
            ev = _to_event(raw)
            if ev and ev.end_datetime_local >= start_date and ev.start_datetime_local <= end_date:
                out.append(ev)
        return sorted(out, key=lambda e: e.start_datetime_local)

    async def async_create_event(self, **kwargs: Any) -> None:
        """Add an event to the family calendar (shared with the whole family)."""
        start, end = kwargs["dtstart"], kwargs["dtend"]
        all_day = not isinstance(start, datetime)
        if all_day:
            start_iso = datetime.combine(start, datetime.min.time(), dt_util.get_default_time_zone()).isoformat()
            end_iso = datetime.combine(end, datetime.min.time(), dt_util.get_default_time_zone()).isoformat()
        else:
            start_iso, end_iso = dt_util.as_utc(start).isoformat(), dt_util.as_utc(end).isoformat()
        payload = {
            "title": kwargs.get("summary") or "Event",
            "description": kwargs.get("description") or "",
            "location": kwargs.get("location") or "",
            "startDate": start_iso,
            "endDate": end_iso,
            "allDay": all_day,
            "sharing": {"audience": "family"},
        }
        try:
            await self.coordinator.api.create_event(payload)
        except FamilyLifeError as err:
            raise HomeAssistantError(f"Family Life refused the event: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_delete_event(self, uid: str, recurrence_id: str | None = None, recurrence_range: str | None = None) -> None:
        """Delete a Family Life event (connected Google/Outlook/Apple events are read-only)."""
        try:
            await self.coordinator.api.delete_event(uid)
        except FamilyLifeError as err:
            raise HomeAssistantError(f"Family Life refused the delete: {err}") from err
        await self.coordinator.async_request_refresh()
