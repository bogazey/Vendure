/*
 * Captions for the built-in player.
 *
 *   Captions.load(url, cb)           fetch a WebVTT or SRT file -> cb(error, cues)
 *   Captions.find(cues, time, hint)  index of the cue showing at `time` (or -1)
 *   Captions.translate(cues, from, cb)
 *        Translate the next stretch of cues into Arabic (stored on cue.ar).
 *        Needs a Google Cloud Translation API key in js/local-config.js (see README).
 *
 * Plain ES5 for older Tizen TVs.
 */
var Captions = (function () {
    var BATCH = 60;   // cues per translation request

    function stamp(value) {
        // "01:02:03.456", "02:03.456" or "01:02:03,456" -> seconds
        var parts = value.replace(',', '.').split(':');
        var total = 0;
        for (var i = 0; i < parts.length; i++) { total = total * 60 + parseFloat(parts[i]); }
        return total;
    }

    function clean(text) {
        return text.replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
            .replace(/&nbsp;/g, ' ').replace(/^\s+|\s+$/g, '');
    }

    function parse(raw) {
        var blocks = raw.replace(/\r/g, '').split(/\n\s*\n/);
        var cues = [];
        for (var b = 0; b < blocks.length; b++) {
            var lines = blocks[b].split('\n');
            for (var l = 0; l < lines.length; l++) {
                var m = /([\d:.,]+)\s*-->\s*([\d:.,]+)/.exec(lines[l]);
                if (!m) { continue; }
                var text = clean(lines.slice(l + 1).join('\n'));
                if (text) { cues.push({ start: stamp(m[1]), end: stamp(m[2]), text: text }); }
                break;
            }
        }
        cues.sort(function (a, b2) { return a.start - b2.start; });
        return cues;
    }

    function load(url, cb) {
        var xhr = new XMLHttpRequest();
        xhr.open('GET', url, true);
        xhr.timeout = 20000;
        xhr.onload = function () {
            if (xhr.status < 200 || xhr.status >= 300) { cb('network'); return; }
            var cues = parse(xhr.responseText || '');
            cb(cues.length ? null : 'empty', cues);
        };
        xhr.onerror = function () { cb('network'); };
        xhr.ontimeout = function () { cb('network'); };
        xhr.send();
    }

    function find(cues, time, hint) {
        var i = hint >= 0 && hint < cues.length && cues[hint].start <= time ? hint : 0;
        for (; i < cues.length; i++) {
            if (cues[i].start > time) { break; }
            if (time < cues[i].end) { return i; }
        }
        return -1;
    }

    function apiKey() {
        return typeof LOCAL_CONFIG !== 'undefined' && LOCAL_CONFIG.translateApiKey ? LOCAL_CONFIG.translateApiKey : '';
    }

    var busy = false;

    // cb(error) — 'no-key' when no API key is configured.
    function translate(cues, from, cb) {
        cb = cb || function () {};
        var key = apiKey();
        if (!key) { cb('no-key'); return; }
        if (busy) { cb(null); return; }

        var batch = [];
        for (var i = Math.max(0, from); i < cues.length && batch.length < BATCH; i++) {
            if (cues[i].ar === undefined) { batch.push(i); }
        }
        if (!batch.length) { cb(null); return; }

        var body = 'target=ar&source=en&format=text';
        for (var j = 0; j < batch.length; j++) { body += '&q=' + encodeURIComponent(cues[batch[j]].text); }

        busy = true;
        var xhr = new XMLHttpRequest();
        xhr.open('POST', 'https://translation.googleapis.com/language/translate/v2?key=' + encodeURIComponent(key), true);
        xhr.timeout = 20000;
        xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
        xhr.onload = function () {
            busy = false;
            try {
                var out = JSON.parse(xhr.responseText).data.translations;
                for (var k = 0; k < batch.length && k < out.length; k++) {
                    var tmp = document.createElement('textarea');
                    tmp.innerHTML = out[k].translatedText;
                    cues[batch[k]].ar = tmp.value;
                }
                cb(null);
            } catch (e) {
                cb('translate');
            }
        };
        xhr.onerror = function () { busy = false; cb('translate'); };
        xhr.ontimeout = function () { busy = false; cb('translate'); };
        xhr.send(body);
    }

    return { load: load, find: find, translate: translate, hasKey: function () { return !!apiKey(); } };
})();
