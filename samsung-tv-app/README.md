# Watchlist TV — Samsung (Tizen) TV app

A home screen for your podcasts, TV shows and YouTube channels. Pick one to see its
latest episodes; pick an episode and it opens in the TV's YouTube app.

- Rows of tiles, driven with the remote's arrows, OK and BACK.
- Episodes come from YouTube's public feed (latest 15 per channel or playlist) — no account or API key.
- "Open in YouTube" on each item opens the whole channel or playlist.

## Change the collection

Edit `js/collection.js`. Each item needs a title, a type and an ID:

```js
{ title: 'Kurzgesagt', type: 'channel',  id: 'UCsXVk37bltHxD1rDPwtNM8Q' },
{ title: 'My series',  type: 'playlist', id: 'PLxxxxxxxxxxxxxxxx' },
```

- **Playlist ID**: open the playlist on youtube.com; it is the part after `list=` in the address.
- **Channel ID**: open the channel page on a computer, choose *More / About → Share channel → Copy channel ID*.
  It starts with `UC`. (A `@handle` will not work.)
- Optional: `note` (short description) and `image` (the tile's logo: a file you put in `images/logos/`, or a web address).
  The 74 shipped logos are the channels' own YouTube profile pictures, saved inside the app.

The library ships with 74 hand-picked channels in six rows (Podcasts, TV Shows, Documentaries,
Science & Learning, Tech & Engineering, Food & Travel). Every ID was checked against YouTube's
feed in November 2026. If a channel is later removed, the app says so on that item's episode screen.

## Install on the TV

Samsung only lets signed apps install, and the signature is tied to your TV, so the
package has to be built on your computer:

1. Install **Tizen Studio** with the *TV Extensions* and *Samsung Certificate Extension* packages.
2. On the TV: *Apps* → type `12345` on the remote → turn **Developer mode** on, enter your
   computer's IP address, then restart the TV.
3. In Tizen Studio: *Device Manager → Remote Device Manager* → add the TV's IP address and connect.
4. *Certificate Manager* → create a **Samsung** certificate profile (needs a free Samsung account;
   it picks up the connected TV's ID automatically).
5. *File → Import → Tizen → Tizen Project* → choose this `samsung-tv-app` folder (profile: tv).
6. Right-click the project → *Run As → Tizen Web Application*. The app installs and starts,
   and stays in the TV's app list.

## Try it on a computer first

Open `index.html` in Chrome. Arrow keys, Enter and Esc stand in for the remote, and items
open on youtube.com instead of the TV app. Episode lists do not load there, because a normal
browser blocks the cross-site feed request; the TV app is allowed to make it.

## Not yet verified on a real TV

The app was tested in a desktop browser with a simulated remote, feed and Tizen API.
Opening a specific video relies on the YouTube TV app accepting a `v=<id>` / `list=<id>`
deep link; Samsung does not document this officially. If your TV's YouTube app ignores it,
YouTube still opens, but on its home screen. The launch code is in `js/youtube.js`.
