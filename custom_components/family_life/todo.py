"""To-do lists: every Family Life list (shopping, to-do) and a chores list per member."""

from __future__ import annotations

from typing import Any

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity, TodoListEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FamilyLifeConfigEntry
from .api import FamilyLifeError
from .entity import FamilyLifeEntity
from .logic import chores_for, parse_day

ANYONE = "__anyone__"


async def async_setup_entry(hass: HomeAssistant, entry: FamilyLifeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    """Lists and per-member chores, added as they appear on the board."""
    coordinator = entry.runtime_data.coordinator
    known: set[str] = set()

    @callback
    def _sync() -> None:
        new: list[TodoListEntity] = []
        for lst in coordinator.data.get("lists", []):
            key = f"list_{lst['id']}"
            if key not in known:
                known.add(key)
                new.append(FamilyLifeListTodo(coordinator, lst["id"], lst.get("name") or "List"))
        members = [(m["id"], m.get("name") or "Member") for m in coordinator.data.get("members", []) if m.get("id")]
        for member_id, name in [(ANYONE, "Anyone"), *members]:
            key = f"chores_{member_id}"
            if key not in known:
                known.add(key)
                new.append(FamilyLifeChoresTodo(coordinator, None if member_id == ANYONE else member_id, f"Chores: {name}"))
        if new:
            async_add_entities(new)

    _sync()
    entry.async_on_unload(coordinator.async_add_listener(_sync))


class FamilyLifeListTodo(FamilyLifeEntity, TodoListEntity):
    """A shared Family Life list."""

    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM | TodoListEntityFeature.UPDATE_TODO_ITEM | TodoListEntityFeature.DELETE_TODO_ITEM
    )

    def __init__(self, coordinator, list_id: str, name: str) -> None:
        """Initialize."""
        super().__init__(coordinator, f"list_{list_id}")
        self._list_id = list_id
        self._attr_name = name

    def _list(self) -> dict[str, Any] | None:
        return next((l for l in self.coordinator.data.get("lists", []) if l.get("id") == self._list_id), None)

    @property
    def available(self) -> bool:
        """Gone from Family Life = unavailable (deleted lists are not silently kept)."""
        return super().available and self._list() is not None

    @property
    def todo_items(self) -> list[TodoItem] | None:
        """Items on the list."""
        lst = self._list()
        if lst is None:
            return None
        return [
            TodoItem(
                uid=i["id"],
                summary=i.get("text", "") + (f" × {i['quantity']}" if i.get("quantity") else ""),
                status=TodoItemStatus.COMPLETED if i.get("checked") else TodoItemStatus.NEEDS_ACTION,
            )
            for i in lst.get("items", [])
        ]

    async def _call(self, coro) -> None:
        try:
            await coro
        except FamilyLifeError as err:
            raise HomeAssistantError(f"Family Life refused that: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Add an item ("add milk to the shopping list")."""
        await self._call(self.coordinator.api.add_item(self._list_id, item.summary or ""))

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Check / uncheck, or rename."""
        current = next((i for i in (self._list() or {}).get("items", []) if i["id"] == item.uid), None)
        patch: dict[str, Any] = {"checked": item.status == TodoItemStatus.COMPLETED}
        if current is not None and item.summary and item.summary != current.get("text"):
            patch["text"] = item.summary
        await self._call(self.coordinator.api.update_item(self._list_id, item.uid or "", patch))

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Remove items."""
        for uid in uids:
            await self._call(self.coordinator.api.delete_item(self._list_id, uid))


class FamilyLifeChoresTodo(FamilyLifeEntity, TodoListEntity):
    """Open chores for one member (or unassigned). Completing one ticks it off in Family Life."""

    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM | TodoListEntityFeature.UPDATE_TODO_ITEM | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
    )

    def __init__(self, coordinator, member_id: str | None, name: str) -> None:
        """member_id None = chores anyone can do."""
        super().__init__(coordinator, f"chores_{member_id or 'anyone'}")
        self._member_id = member_id
        self._attr_name = name

    @property
    def todo_items(self) -> list[TodoItem] | None:
        """Open chores."""
        return [
            TodoItem(uid=c["id"], summary=c.get("title", ""), status=TodoItemStatus.NEEDS_ACTION, due=parse_day(c.get("dueDate")))
            for c in chores_for(self.coordinator.data, self._member_id)
        ]

    async def _call(self, coro) -> None:
        try:
            await coro
        except FamilyLifeError as err:
            raise HomeAssistantError(f"Family Life refused that: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Add a chore for this member."""
        due = item.due.isoformat()[:10] if item.due else None
        await self._call(self.coordinator.api.create_chore(item.summary or "Chore", self._member_id, due))

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Completing = done in Family Life (a recurring chore comes back on its next day)."""
        if item.status == TodoItemStatus.COMPLETED:
            await self._call(self.coordinator.api.complete_chore(item.uid or ""))
            return
        patch: dict[str, Any] = {}
        if item.summary:
            patch["title"] = item.summary
        if item.due:
            patch["dueDate"] = item.due.isoformat()[:10]
        if patch:
            await self._call(self.coordinator.api.update_chore(item.uid or "", patch))

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete chores (adults only in Family Life; the connecting parent is one)."""
        for uid in uids:
            await self._call(self.coordinator.api.delete_chore(uid))
