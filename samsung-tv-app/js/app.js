/*
 * Screens and remote-control navigation. Plain ES5 for older Tizen TVs.
 */
(function () {
    var KEY = { LEFT: 37, UP: 38, RIGHT: 39, DOWN: 40, ENTER: 13, BACK: 10009, ESC: 27, BACKSPACE: 8 };
    var ROW_HEIGHT = 430;
    var CARD_STEP = 290;      // card width + margin
    var GRID_COLS = 4;
    var EP_STEP = 300;        // episode tile height + margin
    var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    var sections = [];
    for (var s = 0; s < COLLECTION.length; s++) {
        if (COLLECTION[s].items && COLLECTION[s].items.length) { sections.push(COLLECTION[s]); }
    }

    var screen = 'home';
    var home = { row: 0, cols: [] };
    var detail = { item: null, episodes: [], focus: -1, token: 0 };   // focus -1 = "Open in YouTube" button
    var toastTimer = null;

    function $(id) { return document.getElementById(id); }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) { node.className = className; }
        if (text) { node.appendChild(document.createTextNode(text)); }
        return node;
    }

    function setTransform(node, value) {
        node.style.webkitTransform = value;
        node.style.transform = value;
    }

    /* ---------- tiles ---------- */

    function initials(title) {
        var words = title.replace(/^the\s+/i, '').split(/\s+/);
        var out = '';
        for (var i = 0; i < words.length && out.length < 2; i++) {
            if (words[i]) { out += words[i].charAt(0).toUpperCase(); }
        }
        return out;
    }

    function hue(title) {
        var h = 0;
        for (var i = 0; i < title.length; i++) { h = (h * 31 + title.charCodeAt(i)) % 360; }
        return h;
    }

    function paintTile(tile, item) {
        var h = hue(item.title);
        tile.innerHTML = '';
        tile.style.background = 'linear-gradient(135deg, hsl(' + h + ',55%,42%), hsl(' + ((h + 40) % 360) + ',60%,24%))';
        tile.style.webkitBackgroundClip = 'padding-box';   // keep the colour out of the focus border
        tile.style.backgroundClip = 'padding-box';
        tile.appendChild(document.createTextNode(initials(item.title)));
        if (item.image) {
            var img = el('img');
            img.onerror = function () { if (img.parentNode) { img.parentNode.removeChild(img); } };
            img.src = item.image;
            tile.appendChild(img);
        }
    }

    /* ---------- home ---------- */

    function buildHome() {
        var rows = $('rows');
        if (!sections.length) {
            rows.appendChild(el('div', 'row-title', 'Your collection is empty. Add items in js/collection.js.'));
            return;
        }
        for (var r = 0; r < sections.length; r++) {
            home.cols.push(0);
            var row = el('div', 'row');
            row.appendChild(el('div', 'row-title', sections[r].title));
            var clip = el('div', 'row-clip');
            var track = el('div', 'row-track');
            for (var c = 0; c < sections[r].items.length; c++) {
                var item = sections[r].items[c];
                var card = el('div', 'card');
                var tile = el('div', 'tile');
                paintTile(tile, item);
                card.appendChild(tile);
                card.appendChild(el('div', 'card-title', item.title));
                card.onclick = (function (rr, cc) {
                    return function () { home.row = rr; home.cols[rr] = cc; renderHome(); openDetail(); };
                })(r, c);
                track.appendChild(card);
            }
            clip.appendChild(track);
            row.appendChild(clip);
            rows.appendChild(row);
        }
        renderHome();
    }

    function renderHome() {
        var rows = $('rows').children;
        for (var r = 0; r < rows.length; r++) {
            var active = r === home.row;
            rows[r].className = active ? 'row active' : 'row';
            var track = rows[r].getElementsByClassName('row-track')[0];
            var cards = track.children;
            for (var c = 0; c < cards.length; c++) {
                cards[c].className = active && c === home.cols[r] ? 'card focused' : 'card';
            }
            // Keep the focused card on screen: 6 cards fit, scroll once we pass the 5th.
            var shift = Math.max(0, home.cols[r] - 4) * CARD_STEP;
            setTransform(track, 'translateX(' + -shift + 'px)');
        }
        // Two rows fit on screen; keep the active row in view.
        var top = Math.max(0, Math.min(home.row, rows.length - 2)) * ROW_HEIGHT;
        setTransform($('rows'), 'translateY(' + -top + 'px)');
    }

    function homeKey(code) {
        if (!sections.length) { return; }
        var count = sections[home.row].items.length;
        if (code === KEY.LEFT && home.cols[home.row] > 0) { home.cols[home.row]--; }
        else if (code === KEY.RIGHT && home.cols[home.row] < count - 1) { home.cols[home.row]++; }
        else if (code === KEY.UP && home.row > 0) { home.row--; }
        else if (code === KEY.DOWN && home.row < sections.length - 1) { home.row++; }
        else if (code === KEY.ENTER) { openDetail(); return; }
        renderHome();
    }

    /* ---------- detail ---------- */

    function formatDate(iso) {
        var d = new Date(iso);
        if (isNaN(d.getTime())) { return ''; }
        return d.getDate() + ' ' + MONTHS[d.getMonth()] + ' ' + d.getFullYear();
    }

    function isFeed(item) { return item.type === 'feed'; }

    function formatLength(seconds) {
        var minutes = Math.round(seconds / 60);
        return minutes < 60 ? minutes + ' min' : Math.floor(minutes / 60) + ' h ' + (minutes % 60) + ' min';
    }

    function openDetail() {
        var section = sections[home.row];
        var item = section.items[home.cols[home.row]];
        detail.item = item;
        detail.episodes = [];
        detail.focus = -1;
        var token = ++detail.token;

        paintTile($('detail-tile'), item);
        $('detail-kind').textContent = section.title;
        $('detail-title').textContent = item.title;
        $('detail-note').textContent = item.note || '';
        $('grid').innerHTML = '';
        $('status').textContent = 'Loading episodes…';
        $('open-btn').textContent = isFeed(item) ? 'Play latest episode' : 'Open in YouTube';

        screen = 'detail';
        $('home').className = 'screen hidden';
        $('detail').className = 'screen';
        renderDetail();

        (isFeed(item) ? Feeds : YT).loadEpisodes(item, function (err, episodes) {
            if (token !== detail.token) { return; }   // user already left this screen
            if (err && isFeed(item)) {
                $('status').textContent = 'Could not load this show\'s episode list. Check the TV\'s internet connection and try again.';
                return;
            }
            if (err === 'not-found') {
                $('status').textContent = 'YouTube has no ' + item.type + ' with the ID "' + item.id + '". Check it in js/collection.js.';
                return;
            }
            if (err) {
                $('status').textContent = 'Could not load episodes. Check the TV\'s internet connection, or use "Open in YouTube".';
                return;
            }
            if (!episodes.length) {
                $('status').textContent = isFeed(item) ? 'This show has no playable episodes yet.' : 'No episodes found yet. Use "Open in YouTube" to browse.';
                return;
            }
            $('status').textContent = '';
            detail.episodes = episodes;
            buildGrid();
            detail.focus = 0;
            renderDetail();
        });
    }

    function buildGrid() {
        var grid = $('grid');
        grid.innerHTML = '';
        for (var i = 0; i < detail.episodes.length; i++) {
            var ep = detail.episodes[i];
            var node = el('div', 'ep');
            var thumb = el('div', 'ep-thumb');
            var img = el('img');
            img.onerror = (function (image) { return function () { image.style.display = 'none'; }; })(img);
            img.src = ep.thumb || detail.item.image || '';
            thumb.appendChild(img);
            node.appendChild(thumb);
            node.appendChild(el('div', 'ep-title', ep.title));
            node.appendChild(el('div', 'ep-date', formatDate(ep.published) + (ep.duration ? '  ·  ' + formatLength(ep.duration) : '')));
            node.onclick = (function (index) {
                return function () { detail.focus = index; renderDetail(); playFocused(); };
            })(i);
            grid.appendChild(node);
        }
    }

    function renderDetail() {
        $('open-btn').className = detail.focus === -1 ? 'btn focused' : 'btn';
        var nodes = $('grid').children;
        for (var i = 0; i < nodes.length; i++) {
            nodes[i].className = i === detail.focus ? 'ep focused' : 'ep';
        }
        // Two full rows of episodes fit; scroll so the focused row stays visible.
        var row = detail.focus < 0 ? 0 : Math.floor(detail.focus / GRID_COLS);
        setTransform($('grid'), 'translateY(' + -(Math.max(0, row - 1) * EP_STEP) + 'px)');
    }

    function closeDetail() {
        detail.token++;
        screen = 'home';
        $('detail').className = 'screen hidden';
        $('home').className = 'screen';
        renderHome();
    }

    function launched(err, method) {
        if (err) { toast('Could not open YouTube. Is the YouTube app installed on this TV?'); return; }
        // Remember which way of opening YouTube this TV accepted; handy when reporting problems.
        try { localStorage.setItem('yt:lastMethod', method || ''); } catch (e) { /* ignore */ }
    }

    // Independent shows play inside the app.
    function playInApp(episode) {
        screen = 'player';
        Player.open(episode, detail.item, function (reason) {
            screen = 'detail';
            renderDetail();
            if (reason === 'error') { toast('This episode could not be played on this TV.'); }
        });
    }

    function playFocused() {
        if (isFeed(detail.item)) {
            var episode = detail.episodes[detail.focus === -1 ? 0 : detail.focus];
            if (episode) { playInApp(episode); }
            return;
        }
        if (detail.focus === -1) {
            toast('Opening ' + detail.item.title + ' in YouTube…');
            YT.openItem(detail.item, launched);
        } else {
            toast('Opening in YouTube…');
            YT.openVideo(detail.episodes[detail.focus].id, launched);
        }
    }

    function detailKey(code) {
        var n = detail.episodes.length;
        var f = detail.focus;
        if (code === KEY.ENTER) { playFocused(); return; }
        if (f === -1) {
            if ((code === KEY.RIGHT || code === KEY.DOWN) && n) { detail.focus = 0; }
        } else if (code === KEY.LEFT) {
            detail.focus = f % GRID_COLS === 0 ? -1 : f - 1;
        } else if (code === KEY.RIGHT) {
            if (f % GRID_COLS < GRID_COLS - 1 && f < n - 1) { detail.focus = f + 1; }
        } else if (code === KEY.UP) {
            if (f >= GRID_COLS) { detail.focus = f - GRID_COLS; }
        } else if (code === KEY.DOWN) {
            if (f + GRID_COLS < n) { detail.focus = f + GRID_COLS; }
            else if (Math.floor(f / GRID_COLS) < Math.floor((n - 1) / GRID_COLS)) { detail.focus = n - 1; }
        }
        renderDetail();
    }

    /* ---------- shared ---------- */

    function toast(message) {
        var node = $('toast');
        node.textContent = message;
        node.className = '';
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () { node.className = 'hidden'; }, 4000);
    }

    function tick() {
        var d = new Date();
        var m = d.getMinutes();
        $('clock').textContent = d.getHours() + ':' + (m < 10 ? '0' + m : m);
    }

    function exitApp() {
        try { tizen.application.getCurrentApplication().exit(); } catch (e) { /* not on a TV */ }
    }

    document.addEventListener('keydown', function (e) {
        var code = e.keyCode;
        if (screen === 'player') { e.preventDefault(); Player.key(code); return; }
        var isBack = code === KEY.BACK || code === KEY.ESC || code === KEY.BACKSPACE;
        if (isBack) {
            e.preventDefault();
            if (screen === 'detail') { closeDetail(); } else { exitApp(); }
            return;
        }
        if (code >= KEY.LEFT && code <= KEY.DOWN) { e.preventDefault(); }
        if (screen === 'home') { homeKey(code); } else { detailKey(code); }
    });

    $('open-btn').onclick = function () { detail.focus = -1; renderDetail(); playFocused(); };

    buildHome();
    tick();
    setInterval(tick, 15000);
})();
