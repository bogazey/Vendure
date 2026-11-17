/*
 * Everything that talks to YouTube:
 *   - YT.loadEpisodes(item, cb)  latest videos of a channel/playlist (public RSS feed, no API key)
 *   - YT.openVideo(id, cb)       open one video in the TV's YouTube app
 *   - YT.openItem(item, cb)      open the whole channel/playlist in the YouTube app
 *
 * Written in plain ES5 so it also runs on older Tizen TVs.
 */
var YT = (function () {
    // The YouTube app on Samsung TVs. Newer firmware uses the first id, some models the second.
    var APP_IDS = ['111299001912', '9Ur5IzDKqV.TizenYouTube'];
    var FEED = 'https://www.youtube.com/feeds/videos.xml';
    var CACHE_MS = 30 * 60 * 1000;

    function hasTizen() {
        return typeof tizen !== 'undefined' && tizen.application;
    }

    /* ---------- episodes ---------- */

    // Feeds to try, in order. For a channel, "UULF" + the rest of its id is YouTube's list of
    // full-length uploads (no Shorts, no live streams); the plain channel feed is the fallback.
    function feedUrls(item) {
        if (item.type === 'playlist') { return [FEED + '?playlist_id=' + encodeURIComponent(item.id)]; }
        var urls = [];
        if (item.id.indexOf('UC') === 0) { urls.push(FEED + '?playlist_id=' + encodeURIComponent('UULF' + item.id.substring(2))); }
        urls.push(FEED + '?channel_id=' + encodeURIComponent(item.id));
        return urls;
    }

    function isShort(entry) {
        var links = entry.getElementsByTagName('link');
        for (var i = 0; i < links.length; i++) {
            if ((links[i].getAttribute('href') || '').indexOf('/shorts/') >= 0) { return true; }
        }
        return false;
    }

    function firstText(node, names) {
        for (var i = 0; i < names.length; i++) {
            var found = node.getElementsByTagName(names[i]);
            if (found.length && found[0].textContent) { return found[0].textContent; }
        }
        return '';
    }

    function parseFeed(xml) {
        var entries = xml.getElementsByTagName('entry');
        var out = [];
        for (var i = 0; i < entries.length; i++) {
            var id = firstText(entries[i], ['yt:videoId', 'videoId']);
            if (!id || isShort(entries[i])) { continue; }
            out.push({
                id: id,
                title: firstText(entries[i], ['title']),
                published: firstText(entries[i], ['published']),
                thumb: 'https://i.ytimg.com/vi/' + id + '/mqdefault.jpg',
                backdrop: 'https://i.ytimg.com/vi/' + id + '/maxresdefault.jpg',
                description: firstText(entries[i], ['media:description', 'description']).substring(0, 400)
            });
        }
        return out;
    }

    function readCache(key) {
        try {
            var hit = JSON.parse(localStorage.getItem(key));
            if (hit && Date.now() - hit.at < CACHE_MS) { return hit.episodes; }
        } catch (e) { /* no cache available */ }
        return null;
    }

    function writeCache(key, episodes) {
        try { localStorage.setItem(key, JSON.stringify({ at: Date.now(), episodes: episodes })); } catch (e) { /* ignore */ }
    }

    // cb(error, episodes)
    function loadEpisodes(item, cb) {
        var key = 'feed3:' + item.type + ':' + item.id;
        var cached = readCache(key);
        if (cached) { cb(null, cached); return; }

        var urls = feedUrls(item);
        var attempt = 0;
        function tryNext(lastError) {
            if (attempt >= urls.length) { cb(lastError); return; }
            fetchFeed(urls[attempt++], function (err, episodes) {
                // An empty full-length list (e.g. a channel that only posts Shorts) also falls through.
                if (err || (!episodes.length && attempt < urls.length)) { tryNext(err || 'not-found'); return; }
                writeCache(key, episodes);
                cb(null, episodes);
            });
        }
        tryNext('not-found');
    }

    function fetchFeed(url, cb) {
        var xhr = new XMLHttpRequest();
        xhr.open('GET', url, true);
        xhr.timeout = 15000;
        xhr.onload = function () {
            if (xhr.status === 404) { cb('not-found'); return; }
            if (xhr.status < 200 || xhr.status >= 300) { cb('network'); return; }
            var xml = xhr.responseXML;
            if (!xml) {
                try { xml = new DOMParser().parseFromString(xhr.responseText, 'text/xml'); } catch (e) { xml = null; }
            }
            if (!xml) { cb('network'); return; }
            cb(null, parseFeed(xml));
        };
        xhr.onerror = function () { cb('network'); };
        xhr.ontimeout = function () { cb('network'); };
        xhr.send();
    }

    /* ---------- opening the YouTube app ---------- */

    /*
     * Method 1: the TV's casting service (DIAL), the same path a phone uses to cast a video.
     * POST "v=VIDEO_ID" to the TV's own YouTube endpoint on port 8080; 201 means YouTube took it.
     */
    function tvAddresses() {
        var hosts = [];
        try {
            var ip = webapis.network.getIp();
            if (ip) { hosts.push(ip); }
        } catch (e) { /* Samsung web APIs not available */ }
        hosts.push('127.0.0.1');
        return hosts;
    }

    function dial(query, cb) {
        var hosts = tvAddresses();
        var i = 0;
        function next() {
            if (i >= hosts.length) { cb(false); return; }
            var xhr = new XMLHttpRequest();
            var done = false;
            function finish(ok) { if (done) { return; } done = true; if (ok) { cb(true); } else { next(); } }
            try {
                xhr.open('POST', 'http://' + hosts[i++] + ':8080/ws/apps/YouTube', true);
                xhr.timeout = 4000;
                xhr.setRequestHeader('Content-Type', 'text/plain; charset=utf-8');
                xhr.onload = function () { finish(xhr.status === 200 || xhr.status === 201); };
                xhr.onerror = function () { finish(false); };
                xhr.ontimeout = function () { finish(false); };
                xhr.send(query);
            } catch (e) {
                finish(false);
            }
        }
        next();
    }

    // The YouTube TV app takes its deep link as a query string, e.g. "v=VIDEO_ID" or "list=PLAYLIST_ID".
    function launch(query, webUrl, cb) {
        cb = cb || function () {};

        if (!hasTizen()) {
            // Not on a TV (testing in a desktop browser): open the normal website instead.
            window.open(webUrl, '_blank');
            cb(null);
            return;
        }

        dial(query, function (ok) {
            if (ok) { cb(null, 'dial'); } else { appControl(query, cb); }
        });
    }

    // Method 2: Tizen app control with the query as payload. On some TVs YouTube ignores it and opens its home screen.
    function appControl(query, cb) {
        var data = [new tizen.ApplicationControlData('PAYLOAD', [JSON.stringify({ values: query })])];
        var control = new tizen.ApplicationControl('http://tizen.org/appcontrol/operation/view', null, null, null, data);
        var attempt = 0;

        function next() {
            if (attempt >= APP_IDS.length) { plainLaunch(0); return; }
            var appId = APP_IDS[attempt++];
            try {
                tizen.application.launchAppControl(control, appId, function () { cb(null, 'appcontrol'); }, next);
            } catch (e) {
                next();
            }
        }

        // Last resort: just start YouTube without a deep link.
        function plainLaunch(i) {
            if (i >= APP_IDS.length) { cb('no-youtube'); return; }
            try {
                tizen.application.launch(APP_IDS[i], function () { cb(null, 'plain'); }, function () { plainLaunch(i + 1); });
            } catch (e) {
                plainLaunch(i + 1);
            }
        }

        next();
    }

    function openVideo(videoId, cb) {
        launch('v=' + videoId + '&t=0', 'https://www.youtube.com/watch?v=' + videoId, cb);
    }

    function openItem(item, cb) {
        if (item.type === 'playlist') {
            launch('list=' + item.id, 'https://www.youtube.com/playlist?list=' + item.id, cb);
            return;
        }
        // A channel's "uploads" playlist has the same id with UC swapped for UU.
        var uploads = item.id.indexOf('UC') === 0 ? 'UU' + item.id.substring(2) : item.id;
        launch('list=' + uploads, 'https://www.youtube.com/channel/' + item.id, cb);
    }

    return { loadEpisodes: loadEpisodes, openVideo: openVideo, openItem: openItem };
})();
