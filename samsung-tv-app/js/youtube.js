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

    function feedUrl(item) {
        var key = item.type === 'playlist' ? 'playlist_id' : 'channel_id';
        return FEED + '?' + key + '=' + encodeURIComponent(item.id);
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
            if (!id) { continue; }
            out.push({
                id: id,
                title: firstText(entries[i], ['title']),
                published: firstText(entries[i], ['published']),
                thumb: 'https://i.ytimg.com/vi/' + id + '/mqdefault.jpg'
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
        var key = 'feed:' + item.type + ':' + item.id;
        var cached = readCache(key);
        if (cached) { cb(null, cached); return; }

        var xhr = new XMLHttpRequest();
        xhr.open('GET', feedUrl(item), true);
        xhr.timeout = 15000;
        xhr.onload = function () {
            if (xhr.status === 404) { cb('not-found'); return; }
            if (xhr.status < 200 || xhr.status >= 300) { cb('network'); return; }
            var xml = xhr.responseXML;
            if (!xml) {
                try { xml = new DOMParser().parseFromString(xhr.responseText, 'text/xml'); } catch (e) { xml = null; }
            }
            if (!xml) { cb('network'); return; }
            var episodes = parseFeed(xml);
            writeCache(key, episodes);
            cb(null, episodes);
        };
        xhr.onerror = function () { cb('network'); };
        xhr.ontimeout = function () { cb('network'); };
        xhr.send();
    }

    /* ---------- opening the YouTube app ---------- */

    // The YouTube TV app takes its deep link as a query string, e.g. "v=VIDEO_ID" or "list=PLAYLIST_ID".
    function launch(query, webUrl, cb) {
        cb = cb || function () {};

        if (!hasTizen()) {
            // Not on a TV (testing in a desktop browser): open the normal website instead.
            window.open(webUrl, '_blank');
            cb(null);
            return;
        }

        var data = [new tizen.ApplicationControlData('PAYLOAD', [JSON.stringify({ values: query })])];
        var control = new tizen.ApplicationControl('http://tizen.org/appcontrol/operation/view', null, null, null, data);
        var attempt = 0;

        function next() {
            if (attempt >= APP_IDS.length) { plainLaunch(0); return; }
            var appId = APP_IDS[attempt++];
            try {
                tizen.application.launchAppControl(control, appId, function () { cb(null); }, next);
            } catch (e) {
                next();
            }
        }

        // Last resort: just start YouTube without a deep link.
        function plainLaunch(i) {
            if (i >= APP_IDS.length) { cb('no-youtube'); return; }
            try {
                tizen.application.launch(APP_IDS[i], function () { cb(null); }, function () { plainLaunch(i + 1); });
            } catch (e) {
                plainLaunch(i + 1);
            }
        }

        next();
    }

    function openVideo(videoId, cb) {
        launch('v=' + videoId, 'https://www.youtube.com/watch?v=' + videoId, cb);
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
