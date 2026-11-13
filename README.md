# Family Life for Home Assistant

Bring your Family Life family into Home Assistant: the family calendar, chores and shared
shopping / to-do lists, as native Home Assistant calendars, to-do lists and sensors.

- **Calendars**: a family calendar plus one per family member. Events you add from Home Assistant
  are shared with the whole family. Google, Outlook and Apple calendars that family members share
  with the family appear too (read-only).
- **To-do lists**: every Family Life list (for example *Groceries*). Ask your voice assistant to
  "add milk to the groceries list". There is also a chores list per member: completing a chore in
  Home Assistant ticks it off in Family Life, and a recurring chore comes back on its next day.
- **Sensors** for automations: *Next event*, *&lt;name&gt; chores today* and *Overdue chores*.
- **Service** `family_life.complete_chore`.

Requires a Family Life family on the **Family plan or above**, and a **parent** to connect it.

## Install

1. In HACS, open *Custom repositories*, add this repository as an *Integration*, and install
   **Family Life**. Restart Home Assistant.
2. *Settings → Devices & services → Add integration → Family Life*.
3. Leave the server as suggested and continue. Sign in to Family Life as a parent and choose
   **Allow**. You return to Home Assistant and the entities appear.

## Privacy and security

- Sign-in is OAuth 2 with PKCE. Home Assistant never sees your Family Life password, and stores
  only revocable tokens.
- The connection acts as the parent who connected it and can only reach the calendar, chores,
  lists and family members' names and colours. It can never reach finances, health records or
  documents.
- Disconnect any time in Family Life: *Settings → Smart home → Home Assistant → Disconnect*. Home
  Assistant then asks you to sign in again.
- **Instant updates**: if this Home Assistant has a public https address (Home Assistant Cloud, or
  your own), Family Life sends a signed "something changed" ping to it and Home Assistant refreshes
  straight away. The ping contains no family data. Without a public address, Home Assistant
  refreshes every 5 minutes.

## Show the family board on a wall display

Family Life also has a full-screen family board for wall tablets: open `/hub` on the Family Life
website on the tablet and pair it from *Settings → Smart home → Hub displays*. To show the board
inside a Home Assistant dashboard, add a *Webpage* card pointing at that same `/hub` address and
pair it once.

## Development

```bash
pip install -r requirements_test.txt
pytest
```
