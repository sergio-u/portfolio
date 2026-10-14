---
name: gws-calendar-flights
description: "Google Calendar: Add flight itineraries and trip blocks from booking confirmations."
user-invocable: false
---

# calendar flights recipe

Add flight itineraries and trip blocks to Google Calendar from booking confirmations.

## Pattern

For a round-trip with flights + trip block, create 3 events:

1. **Outbound flight** -- timed event with departure/arrival in local timezones
2. **Trip block** -- all-day event spanning the destination stay
3. **Return flight** -- timed event with departure/arrival in local timezones

## Outbound / Return Flight

```bash
gws calendar +insert \
  --summary '✈️ SEA → JFK (Delta DL461)' \
  --start '2026-06-13T15:55:00-07:00' \
  --end '2026-06-14T00:18:00-04:00' \
  --location 'Seattle-Tacoma International Airport (SEA)' \
  --description 'Delta DL461 | Nonstop 5h 23m
Confirmation: GPCNM5
Depart: SEA 3:55 PM PDT
Arrive: JFK 12:18 AM EDT (next day)
Fare: Main Basic'
```

**Time zones matter:** Use the departure city's offset for `--start` and the arrival city's offset for `--end`. Common US offsets:
- PDT (Seattle): `-07:00`
- EDT (New York): `-04:00`
- CDT (Chicago): `-05:00`
- MDT (Denver): `-06:00`

## Trip Block (all-day)

Use the raw `events insert` method with `date` (not `dateTime`) for all-day events:

```bash
gws calendar events insert \
  --params '{"calendarId": "primary"}' \
  --json '{
    "summary": "🗽 New York City Trip",
    "description": "Confirmation: GPCNM5",
    "location": "New York City, NY",
    "start": {"date": "2026-06-14"},
    "end": {"date": "2026-06-21"}
  }'
```

Note: `+insert` helper doesn't support all-day events (requires `dateTime`). Use the raw `events insert` method instead.

## Summary format

- Flights: `✈️ <ORIGIN> → <DEST> (<Airline> <Flight#>)`
- Trip block: `🗽 <City> Trip` (use a relevant emoji)
- Include confirmation codes in description, not title

## Description template

```
<Airline> <Flight#> | <Nonstop/1 stop> <Duration>
Confirmation: <Code>
Depart: <Airport> <Time> <TZ>
Arrive: <Airport> <Time> <TZ>
Fare: <Class>
```

## Conventions

- Confirm with user before creating events
- Parse timezone offsets from airport codes (SEA=Pacific, JFK=Eastern, etc.)
- For next-day arrivals, note it in the description
- For one-way flights, skip the trip block
