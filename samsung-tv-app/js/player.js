/*
 * Built-in player for independent shows (video or audio files from the show's own feed).
 *
 *   Player.open(episode, item, onClose)   start playing
 *   Player.key(code)                      remote-control key while the player is open
 *
 * Remote: OK / Play-Pause = pause or resume, LEFT = back 10 s, RIGHT = forward 30 s,
 *         Rewind / Fast-forward = 1 minute, UP = captions (Off / English / Arabic),
 *         BACK or Stop = leave the player.
 * The position is remembered per episode, so an episode resumes where you left it.
 *
 * Plain ES5 for older Tizen TVs.
 */
var Player = (function () {
    var KEY = {
        LEFT: 37, UP: 38, RIGHT: 39, ENTER: 13, SPACE: 32, BACK: 10009, ESC: 27, BACKSPACE: 8,
        PLAY: 415, PAUSE: 19, PLAY_PAUSE: 10252, STOP: 413, REWIND: 412, FAST_FORWARD: 417
    };
    var HIDE_AFTER_MS = 4000;

    var media, current, onClose, hideTimer, saveTimer, isOpen = false;
    var CC_MODES = ['off', 'en', 'ar'];
    var CC_LABELS = { off: 'Captions off', en: 'CC English', ar: 'CC العربية' };
    var cues = null, cueIndex = -1, ccMode = 'off', ccLoading = false;

    try { ccMode = localStorage.getItem('cc:mode') || 'off'; } catch (e) { /* ignore */ }
    if (CC_MODES.indexOf(ccMode) < 0) { ccMode = 'off'; }

    function $(id) { return document.getElementById(id); }

    function clock(total) {
        total = Math.max(0, Math.floor(total || 0));
        var h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60;
        return (h ? h + ':' + (m < 10 ? '0' : '') : '') + m + ':' + (s < 10 ? '0' : '') + s;
    }

    function posKey() { return 'pos:' + current.episode.id; }

    function savePosition() {
        if (!isOpen || !media.duration || isNaN(media.duration)) { return; }
        try {
            // Nothing worth resuming in the first 30 s or the last minute.
            if (media.currentTime > 30 && media.currentTime < media.duration - 60) {
                localStorage.setItem(posKey(), String(Math.floor(media.currentTime)));
            } else {
                localStorage.removeItem(posKey());
            }
        } catch (e) { /* ignore */ }
    }

    function savedPosition() {
        try { return parseInt(localStorage.getItem(posKey()), 10) || 0; } catch (e) { return 0; }
    }

    /* ---------- captions ---------- */

    function renderCaption() {
        var box = $('player-captions');
        if (ccMode === 'off' || !cues || !media) { box.className = 'hidden'; return; }
        var t = media.currentTime;
        cueIndex = Captions.find(cues, t, cueIndex);
        if (cueIndex < 0) { box.className = 'hidden'; }
        else {
            var cue = cues[cueIndex];
            var text = cue.text;
            if (ccMode === 'ar') { text = cue.ar !== undefined ? cue.ar : '…'; }
            $('player-caption-text').textContent = text;
            box.className = (ccMode === 'ar' ? 'rtl' : '') + ($('player-bar').className === 'faded' ? ' low' : '');
        }
        // Keep Arabic translated a little ahead of playback.
        if (ccMode === 'ar') {
            var ahead = cueIndex >= 0 ? cueIndex : Captions.find(cues, t + 30, 0);
            for (var i = Math.max(0, ahead); i < cues.length && i < ahead + 40; i++) {
                if (cues[i].ar === undefined) { Captions.translate(cues, i, ccError); break; }
            }
        }
    }

    function ccError(err) {
        if (!err) { if (/translation|Arabic/.test($('player-status').textContent)) { status(''); } return; }
        if (err === 'no-key') { status('Arabic captions need a translation key (see README)'); }
        else if (err) { status('Arabic translation unavailable right now'); }
    }

    function ccLabel() {
        $('player-cc').textContent = current && current.episode.captions ? CC_LABELS[ccMode] : '';
    }

    function loadCaptions() {
        cues = null; cueIndex = -1;
        ccLabel();
        if (!current.episode.captions) { return; }
        ccLoading = true;
        var episodeId = current.episode.id;
        Captions.load(current.episode.captions, function (err, list) {
            if (!isOpen || current.episode.id !== episodeId) { return; }
            ccLoading = false;
            if (err) { $('player-cc').textContent = 'Captions unavailable'; return; }
            cues = list;
            renderCaption();
        });
    }

    function cycleCaptions() {
        if (!current.episode.captions) { status('No captions for this episode'); return; }
        ccMode = CC_MODES[(CC_MODES.indexOf(ccMode) + 1) % CC_MODES.length];
        try { localStorage.setItem('cc:mode', ccMode); } catch (e) { /* ignore */ }
        status(ccLoading ? 'Loading captions…' : '');
        if (ccMode === 'ar' && !Captions.hasKey()) { ccError('no-key'); }
        ccLabel();
        renderCaption();
    }

    function render() {
        var duration = media.duration && isFinite(media.duration) ? media.duration : (current.episode.duration || 0);
        $('player-time').textContent = clock(media.currentTime) + ' / ' + (duration ? clock(duration) : '--:--');
        $('player-fill').style.width = (duration ? Math.min(100, media.currentTime / duration * 100) : 0) + '%';
        $('player-state').textContent = media.paused ? 'Paused' : 'Playing';
        renderCaption();
    }

    function showBar() {
        $('player-bar').className = '';
        clearTimeout(hideTimer);
        // Keep the bar up for audio (nothing else to look at) and while paused.
        if (current.episode.video) {
            hideTimer = setTimeout(function () {
                if (isOpen && !media.paused) { $('player-bar').className = 'faded'; }
            }, HIDE_AFTER_MS);
        }
    }

    function status(message) {
        $('player-status').textContent = message || '';
    }

    function seek(delta) {
        if (!media.duration || isNaN(media.duration)) { return; }
        media.currentTime = Math.max(0, Math.min(media.duration - 1, media.currentTime + delta));
        render();
    }

    function toggle() {
        if (media.paused) { media.play(); } else { media.pause(); }
    }

    function close(reason) {
        if (!isOpen) { return; }
        savePosition();
        isOpen = false;
        clearTimeout(hideTimer);
        clearInterval(saveTimer);
        media.pause();
        media.removeAttribute('src');
        media.load();
        $('player').className = 'hidden';
        $('player-captions').className = 'hidden';
        cues = null;
        var done = onClose;
        onClose = null;
        if (done) { done(reason); }
    }

    function open(episode, item, closed) {
        media = $('media');
        current = { episode: episode, item: item };
        onClose = closed;
        isOpen = true;

        $('player-show').textContent = item.title;
        $('player-title').textContent = episode.title;
        $('player-fill').style.width = '0%';
        $('player-time').textContent = '';
        $('player-state').textContent = '';
        status('Loading…');

        // Audio episodes show the show's logo instead of a picture.
        var art = $('player-art');
        art.innerHTML = '';
        if (episode.video) {
            art.className = 'hidden';
        } else {
            art.className = '';
            if (item.image) {
                var img = document.createElement('img');
                img.src = item.image;
                art.appendChild(img);
            }
        }

        $('player').className = '';
        showBar();
        loadCaptions();

        var resumeAt = savedPosition();
        media.onloadedmetadata = function () {
            if (resumeAt > 0 && resumeAt < media.duration - 60) { media.currentTime = resumeAt; }
            render();
        };
        media.onplaying = function () { status(''); render(); showBar(); };
        media.onwaiting = function () { status('Loading…'); };
        media.onpause = function () { render(); showBar(); };
        media.ontimeupdate = render;
        media.onended = function () {
            try { localStorage.removeItem(posKey()); } catch (e) { /* ignore */ }
            close('ended');
        };
        media.onerror = function () { close('error'); };

        media.src = episode.url;
        media.load();
        var started = media.play();
        if (started && started['catch']) { started['catch'](function () { /* reported through onerror */ }); }

        clearInterval(saveTimer);
        saveTimer = setInterval(savePosition, 5000);
    }

    function key(code) {
        if (!isOpen) { return; }
        if (code === KEY.BACK || code === KEY.ESC || code === KEY.BACKSPACE || code === KEY.STOP) { close('back'); return; }
        showBar();
        if (code === KEY.ENTER || code === KEY.SPACE || code === KEY.PLAY_PAUSE) { toggle(); }
        else if (code === KEY.PLAY) { media.play(); }
        else if (code === KEY.PAUSE) { media.pause(); }
        else if (code === KEY.UP) { cycleCaptions(); }
        else if (code === KEY.LEFT) { seek(-10); }
        else if (code === KEY.RIGHT) { seek(30); }
        else if (code === KEY.REWIND) { seek(-60); }
        else if (code === KEY.FAST_FORWARD) { seek(60); }
    }

    // Ask the TV to send us the media buttons (they are not delivered by default).
    try {
        var names = ['MediaPlayPause', 'MediaPlay', 'MediaPause', 'MediaStop', 'MediaRewind', 'MediaFastForward'];
        for (var i = 0; i < names.length; i++) { tizen.tvinputdevice.registerKey(names[i]); }
    } catch (e) { /* not on a TV */ }

    return { open: open, key: key };
})();
