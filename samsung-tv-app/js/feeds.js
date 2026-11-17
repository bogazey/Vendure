/*
 * Independent shows: reads a show's own podcast feed (RSS) and returns its episodes,
 * each with a direct link to the video or audio file so the app can play it itself.
 *
 *   Feeds.loadEpisodes(item, cb)   cb(error, episodes)
 *
 * Plain ES5 for older Tizen TVs.
 */
var Feeds = (function () {
    var CACHE_MS = 30 * 60 * 1000;
    var MAX_EPISODES = 50;

    function text(node, name) {
        var found = node.getElementsByTagName(name);
        return found.length && found[0].textContent ? found[0].textContent.replace(/^\s+|\s+$/g, '') : '';
    }

    function attr(node, name, attribute) {
        var found = node.getElementsByTagName(name);
        return found.length ? (found[0].getAttribute(attribute) || '') : '';
    }

    function plain(html) {
        return html.replace(/<[^>]+>/g, ' ').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&#39;|&#8217;/g, "'")
            .replace(/&quot;|&#8220;|&#8221;/g, '"').replace(/\s+/g, ' ').replace(/^\s+|\s+$/g, '').substring(0, 400);
    }

    // "1:02:03", "62:03" or "3723" -> seconds
    function seconds(value) {
        if (!value) { return 0; }
        var parts = String(value).split(':');
        var total = 0;
        for (var i = 0; i < parts.length; i++) { total = total * 60 + (parseFloat(parts[i]) || 0); }
        return Math.round(total);
    }

    function parse(xml) {
        var items = xml.getElementsByTagName('item');
        var out = [];
        for (var i = 0; i < items.length && out.length < MAX_EPISODES; i++) {
            var node = items[i];
            var url = attr(node, 'enclosure', 'url');
            if (!url) { continue; }
            var type = attr(node, 'enclosure', 'type');
            var isVideo = type.indexOf('video') === 0 || /\.(mp4|m4v|mov)(\?|$)/i.test(url);
            var captions = '';
            var transcripts = node.getElementsByTagName('podcast:transcript');
            for (var t = 0; t < transcripts.length && !captions; t++) {
                var tType = transcripts[t].getAttribute('type') || '';
                if (tType === 'text/vtt' || tType === 'application/x-subrip' || tType === 'application/srt') {
                    captions = transcripts[t].getAttribute('url') || '';
                }
            }
            out.push({
                id: text(node, 'guid') || url,
                title: text(node, 'title'),
                published: text(node, 'pubDate'),
                url: url,
                video: isVideo,
                // Audio shows often ship huge square artwork per episode; the show logo is used for those instead.
                thumb: isVideo ? (attr(node, 'media:thumbnail', 'url') || attr(node, 'itunes:image', 'href')) : '',
                description: plain(text(node, 'itunes:summary') || text(node, 'description')),
                captions: captions,
                duration: seconds(text(node, 'itunes:duration') || attr(node, 'media:content', 'duration'))
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

    function loadEpisodes(item, cb) {
        var key = 'rss3:' + item.url;
        var cached = readCache(key);
        if (cached) { cb(null, cached); return; }

        var xhr = new XMLHttpRequest();
        xhr.open('GET', item.url, true);
        xhr.timeout = 30000;
        xhr.onload = function () {
            if (xhr.status === 404 || xhr.status === 410) { cb('not-found'); return; }
            if (xhr.status < 200 || xhr.status >= 300) { cb('network'); return; }
            var xml = null;
            try { xml = new DOMParser().parseFromString(xhr.responseText, 'text/xml'); } catch (e) { xml = null; }
            if (!xml || xml.getElementsByTagName('parsererror').length) { cb('network'); return; }
            var episodes = parse(xml);
            writeCache(key, episodes);
            cb(null, episodes);
        };
        xhr.onerror = function () { cb('network'); };
        xhr.ontimeout = function () { cb('network'); };
        xhr.send();
    }

    return { loadEpisodes: loadEpisodes };
})();
