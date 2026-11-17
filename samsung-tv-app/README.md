# Watchlist TV — Samsung (Tizen) TV app

A home screen for your podcasts, TV shows and YouTube channels. Pick one to see its
latest episodes; pick an episode and it opens in the TV's YouTube app.

- Rows of tiles, driven with the remote's arrows, OK and BACK.
- Episodes come from YouTube's public feed (latest 15 per channel or playlist) — no account or API key.
- "Open in YouTube" on each item opens the whole channel or playlist.

## Using it

- **Tabs** at the top: Home, Shows, Podcasts, Learn, Docs, Food & Travel, Independent. Press UP to reach
  them and LEFT/RIGHT to switch; BACK from anywhere on a page also jumps to the tabs (BACK again exits).
- **Featured episode**: the newest episode in the current tab, with *Watch now* and *All episodes*.
- **Rows**: *Continue watching* (independent shows left part-way), *New from your shows*, *Your favourites*,
  then every section as a row of show logos.
- **Show page**: *Play latest episode*, *Open channel in YouTube*, and ♥ to add or remove a favourite.
  Favourites and progress are stored on the TV.

YouTube episodes open in the YouTube app; independent shows play in the built-in player.

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

The YouTube part of the library ships with 74 hand-picked channels in six rows (Podcasts, TV Shows, Documentaries,
Science & Learning, Tech & Engineering, Food & Travel). Every ID was checked against YouTube's
feed in November 2026. If a channel is later removed, the app says so on that item's episode screen.

## Independent shows (play inside the app)

The first two rows are independent shows that publish their own episode feed. The app reads the
feed, lists the newest 50 episodes and plays the video or audio file itself — YouTube is not involved.

To add one, find the show's podcast feed (RSS) address on its website and add:

```js
{ title: 'My show', type: 'feed', url: 'https://example.com/feed.xml', image: 'images/logos/my-show.jpg' },
```

Player remote keys: OK or Play/Pause pauses and resumes, LEFT goes back 10 s, RIGHT forward 30 s,
Rewind / Fast-forward jump a minute, BACK or Stop leaves. An episode resumes where you left it.

### Captions and Arabic

Press UP in the player to switch captions: Off → English → العربية. The choice is remembered.
Captions only exist where the show publishes them in its feed (`podcast:transcript`, WebVTT or SRT);
for other episodes the player says "No captions for this episode".

Arabic is machine-translated from the English captions as the episode plays, using the Google Cloud
Translation API. It needs your own API key: copy `js/local-config.example.js` to `js/local-config.js`
(not committed) and paste the key in. The first 500,000 characters a month are free.

Only shows that offer a feed with direct media files work. Shows that only embed a player on
their web page cannot be added this way.

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
The built-in player was tested with real feeds but stand-in media files; the shows' actual
MP4 / MP3 files are standard formats Samsung TVs play, but were not played on a TV.
To open a specific video the app first uses the TV's casting service (a DIAL request to port 8080
on the TV, the path a phone uses to cast), then falls back to a Tizen app-control deep link, which on
a UA65DU7000 opened only YouTube's home screen. The casting method is confirmed to open the exact
video on a UA65DU7000 (Tizen 9.0). Neither method is documented by Samsung. The method
that worked last is saved as `yt:lastMethod` in the app's local storage. The code is in `js/youtube.js`.
