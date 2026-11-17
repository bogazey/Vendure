/*
 * Built-in player for independent shows (video or audio files from the show's own feed).
 *
 *   Player.open(episode, item, onClose)   start playing
 *   Player.key(code)                      remote-control key while the player is open
 *
 * Remote: OK / Play-Pause = pause or resume, LEFT = back 10 s, RIGHT = forward 30 s,
 *         Rewind / Fast-forward = 1 minute, UP = captions (Off / English / Arabic),
 *         DOWN = sleep timer (Off / 15 / 30 / 45 / 60 / 90 min),
 *         BACK or Stop = leave the player.
 * The position is remembered per episode, so an episode resumes where you left it.
 *
 * Plain ES5 for older Tizen TVs.
 */
var Player = (function () {
    var KEY = {
        LEFT: 37, UP: 38, RIGHT: 39, DOWN: 40, ENTER: 13, SPACE: 32, BACK: 10009, ESC: 27, BACKSPACE: 8,
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
                rememberContinue(Math.floor(media.currentTime), Math.floor(media.duration));
            } else {
                localStorage.removeItem(posKey());
                rememberContinue(0, 0);
            }
        } catch (e) { /* ignore */ }
    }

    // "Continue" row on the home screen: the last 10 episodes left part-way through.
    function rememberContinue(pos, duration) {
        var list = [];
        try { list = JSON.parse(localStorage.getItem('continue')) || []; } catch (e) { list = []; }
        var kept = [];
        for (var i = 0; i < list.length; i++) {
            if (list[i].episode && list[i].episode.id !== current.episode.id) { kept.push(list[i]); }
        }
        if (pos > 0) {
            var it = current.item;
            kept.unshift({
                item: { title: it.title, type: it.type, url: it.url, id: it.id, image: it.image, note: it.note },
                episode: current.episode, pos: pos, duration: duration
            });
        }
        try { localStorage.setItem('continue', JSON.stringify(kept.slice(0, 10))); } catch (e) { /* ignore */ }
    }

    function savedPosition() {
        try { return parseInt(localStorage.getItem(posKey()), 10) || 0; } catch (e) { return 0; }
    }

    /* ---------- captions ---------- */

    function renderCaption() {
        var box = $('player-captions');
        var low = $('player-bar').className === 'faded' ? ' low' : '';
        if (ccMode === 'off' || !cues || !media) { box.className = 'hidden'; return; }
        var t = media.currentTime;
        cueIndex = Captions.find(cues, t, cueIndex);
        if (cueIndex < 0) { box.className = 'hidden'; }
        else {
            var cue = cues[cueIndex];
            var text = cue.text;
            if (ccMode === 'ar') { text = cue.ar !== undefined ? cue.ar : '…'; }
            $('player-caption-text').textContent = text;
            box.className = (ccMode === 'ar' ? 'rtl' : '') + low;
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
        var has = current && current.episode.captions;
        $('player-cc').innerHTML = has ? '<b>CC</b> ' + (ccMode === 'off' ? 'Off' : ccMode === 'en' ? 'English' : 'العربية') : '<b>CC</b> None';
        $('player-cc').className = 'c cc' + (has && ccMode !== 'off' ? ' on' : '');
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
            if (err) { $('player-cc').innerHTML = '<b>CC</b> Unavailable'; return; }
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
        var pct = duration ? Math.min(100, media.currentTime / duration * 100) : 0;
        $('player-cur').textContent = clock(media.currentTime);
        $('player-left').textContent = duration ? '-' + clock(duration - media.currentTime) : '';
        $('player-fill').style.width = pct + '%';
        $('player-knob').style.left = pct + '%';
        $('player-pp').className = 'c big' + (media.paused ? ' paused' : '');
        renderCaption();
    }

    /* ---------- sleep timer ----------
     * DOWN cycles the timer. While it runs, the screen goes dark after DIM_AFTER_MS without a key press;
     * in the last 30 s the sound fades out, then playback pauses (the position is saved).
     */
    var SLEEP_STEPS = [0, 15, 30, 45, 60, 90];
    var DIM_AFTER_MS = 20000, FADE_MS = 30000;
    var sleepMins = 0, sleepEnd = 0, sleepTimer = null, dimTimer = null;
    try { sleepMins = parseInt(localStorage.getItem('sleep:mins'), 10) || 0; } catch (e) { sleepMins = 0; }
    if (SLEEP_STEPS.indexOf(sleepMins) < 0) { sleepMins = 0; }

    function sleepLabel() {
        var text = 'Off';
        if (sleepEnd) { text = Math.max(1, Math.ceil((sleepEnd - Date.now()) / 60000)) + ' min'; }
        $('player-sleep').innerHTML = '<b>☾</b> ' + text;
        $('player-sleep').className = 'c cc' + (sleepEnd ? ' on' : '');
    }

    function startSleep() {
        clearInterval(sleepTimer);
        media.volume = 1;
        sleepEnd = sleepMins ? Date.now() + sleepMins * 60000 : 0;
        if (sleepEnd) { sleepTimer = setInterval(sleepTick, 1000); }
        sleepLabel();
        scheduleDim();
    }

    function sleepTick() {
        if (!isOpen || !sleepEnd) { return; }
        var left = sleepEnd - Date.now();
        if (left <= 0) {
            clearInterval(sleepTimer);
            sleepEnd = 0;
            media.pause();
            media.volume = 1;
            savePosition();
            status('Sleep timer ended — press OK to keep listening');
            setDim(true);
        } else if (left < FADE_MS) {
            media.volume = Math.max(0, left / FADE_MS);
        }
        sleepLabel();
    }

    function cycleSleep() {
        sleepMins = SLEEP_STEPS[(SLEEP_STEPS.indexOf(sleepMins) + 1) % SLEEP_STEPS.length];
        try { localStorage.setItem('sleep:mins', String(sleepMins)); } catch (e) { /* ignore */ }
        startSleep();
        var message = sleepMins ? 'Sleep timer: stops in ' + sleepMins + ' min' : 'Sleep timer off';
        status(message);
        setTimeout(function () { if ($('player-status').textContent === message) { status(''); } }, 3000);
    }

    function setDim(on) { $('player-dim').className = on ? 'on' : ''; }

    function scheduleDim() {
        clearTimeout(dimTimer);
        setDim(false);
        if (!sleepEnd) { return; }
        dimTimer = setTimeout(function () { if (isOpen && sleepEnd && !media.paused) { setDim(true); } }, DIM_AFTER_MS);
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
        clearInterval(sleepTimer);
        clearTimeout(dimTimer);
        setDim(false);
        media.volume = 1;
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

        $('player-show').textContent = item.title + ' · ' + (episode.video ? 'Video' : 'Audio');
        $('player-title').textContent = episode.title;
        $('player-fill').style.width = '0%';
        $('player-knob').style.left = '0%';
        $('player-cur').textContent = '';
        $('player-left').textContent = '';
        $('player-mini').src = item.image || '';
        $('player-bg').style.backgroundImage = !episode.video && item.image ? 'url(' + item.image + ')' : 'none';
        $('player-resume').className = 'hidden';
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
            if (resumeAt > 0 && resumeAt < media.duration - 60) {
                media.currentTime = resumeAt;
                $('player-resume').textContent = 'Resumed at ' + clock(resumeAt);
                $('player-resume').className = 'pill';
            }
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
        startSleep();
    }

    function key(code) {
        if (!isOpen) { return; }
        if (code === KEY.BACK || code === KEY.ESC || code === KEY.BACKSPACE || code === KEY.STOP) { close('back'); return; }
        // While dark, the first key only wakes the screen (OK after the timer ended also resumes).
        if ($('player-dim').className === 'on') {
            scheduleDim();
            showBar();
            if (code === KEY.ENTER && media.paused) { status(''); startSleep(); media.play(); }
            return;
        }
        scheduleDim();
        showBar();
        if (code === KEY.ENTER || code === KEY.SPACE || code === KEY.PLAY_PAUSE) { toggle(); }
        else if (code === KEY.PLAY) { media.play(); }
        else if (code === KEY.PAUSE) { media.pause(); }
        else if (code === KEY.UP) { cycleCaptions(); }
        else if (code === KEY.DOWN) { cycleSleep(); }
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
