# Kuwait Check-In — Prototype v1

A clickable, in-browser prototype of a Foursquare/Swarm-style local social
map app for Kuwait: browse real Kuwait venues on a map, check in with a
photo, and see it reflected instantly on the venue's feed, your profile, and
the map.

No backend, no database, no auth — everything lives in memory for the
current browser session (refreshing the page resets it back to the seed
data).

## Running it

```bash
npm install
npm run dev
```

Then open the printed local URL (defaults to `http://localhost:5173`).

```bash
npm run build   # type-checks and produces a production build in dist/
```

## What's here

- **Map view** (`/`) — a Leaflet map (free OpenStreetMap tiles, no API key)
  centered on Kuwait with 13 real venues across malls, coffee shops,
  supermarkets, and stores, spread across Salmiya, Kuwait City, Hawally-area,
  Fahaheel, Al Rai, Zahra, and Sharq. Pins are color/icon-coded by category;
  clicking one opens a popup with a link into the venue.
- **Venue detail** (`/venue/:venueId`) — venue info plus a photo grid of
  everyone's check-ins there, and a "Check In" button.
- **Check-in flow** — attach a photo (stored as a local `URL.createObjectURL`,
  no upload) and an optional caption. Submitting creates an in-memory
  `CheckIn` that instantly shows up in the venue's feed, the current user's
  profile, and triggers a pulse animation on that venue's map marker.
- **Profile** (`/profile`) — the mock current user's info, a "places
  visited" passport-style list (visit count + latest photo per venue), and a
  chronological grid of their own check-in photos.

## Data model

Plain in-memory TypeScript objects/state — see `src/data/types.ts`:

- `User` — id, name, username, profilePhoto, bio
- `Venue` — id, name, category, area, lat, lng, coverPhoto
- `CheckIn` — id, userId, venueId, photoUrl, caption?, timestamp

Seed data lives in `src/data/venues.ts`, `src/data/users.ts`, and
`src/data/checkins.ts`. App state (the growing list of check-ins) is held in
a React context in `src/state/AppStateContext.tsx`.

## Out of scope (by design, for this prototype)

Real auth/multi-user accounts, a real backend/database, a real venues API,
search/moderation/notifications, and native mobile packaging.
