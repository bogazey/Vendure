/*
 * Built-in player for independent shows (video or audio files from the show's own feed).
 *
 *   Player.open(episode, item, onClose)   start playing
 *   Player.key(code)                      remote-control key while the player is open
 *
 * Remote: OK / Play-Pause = pause or resume, LEFT = back 10 s, RIGHT = forward 30 s,
 *         Rewind / Fast-forward = 1 minute, BACK or Stop = leave the player.
 * The position is remembered per episode, so an episode resumes where you left it.
 *
 * Plain ES5 for older Tizen TVs.
 */
var Player = (function () {
    var KEY = {
        LEFT: 37, RIGHT: 39, ENTER: 13, SPACE: 32, BACK: 10009, ESC: 27, BACKSPACE: 8,
        PLAY: 415, PAUSE: 19, PLAY_PAUSE: 10252, STOP: 413, REWIND: 412, FAST_FORWARD: 417
    };
    var HIDE_AFTER_MS = 4000;

    var media, current, onClose, hideTimer, saveTimer, isOpen = false;

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

    function render() {
        var duration = media.duration && isFinite(media.duration) ? media.duration : (current.episode.duration || 0);
        $('player-time').textContent = clock(media.currentTime) + ' / ' + (duration ? clock(duration) : '--:--');
        $('player-fill').style.width = (duration ? Math.min(100, media.currentTime / duration * 100) : 0) + '%';
        $('player-state').textContent = media.paused ? 'Paused' : 'Playing';
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
