/*
 * Screens and remote-control navigation. Plain ES5 for older Tizen TVs.
 *
 *   Home / category tabs:  tab bar  ->  featured episode  ->  rows (episodes or shows)
 *   Show page:             buttons  ->  episodes row
 *   Player:                handled by player.js
 */
(function () {
    var KEY = { LEFT: 37, UP: 38, RIGHT: 39, DOWN: 40, ENTER: 13, BACK: 10009, ESC: 27, BACKSPACE: 8 };
    var TAB_ORDER = ['Home', 'Shows', 'Podcasts', 'Learn', 'Docs', 'Food & Travel', 'Independent'];
    var EP_STEP = 448;        // episode card width + margin
    var SHOW_STEP = 194;      // show card width + margin
    var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    var LOAD_AT_ONCE = 4;

    function $(id) { return document.getElementById(id); }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) { node.className = className; }
        if (text) { node.appendChild(document.createTextNode(text)); }
        return node;
    }

    function setTransform(node, value) { node.style.webkitTransform = value; node.style.transform = value; }

    /* ---------- data ---------- */

    var sections = [];
    for (var s = 0; s < COLLECTION.length; s++) {
        if (COLLECTION[s].items && COLLECTION[s].items.length) { sections.push(COLLECTION[s]); }
    }

    var tabs = ['Home'];
    (function () {
        var found = {};
        for (var i = 0; i < sections.length; i++) { found[sections[i].tab || sections[i].title] = true; }
        for (var t = 1; t < TAB_ORDER.length; t++) { if (found[TAB_ORDER[t]]) { tabs.push(TAB_ORDER[t]); delete found[TAB_ORDER[t]]; } }
        for (var name in found) { if (found.hasOwnProperty(name)) { tabs.push(name); } }
    })();

    function itemKey(item) { return item.type + ':' + (item.id || item.url); }
    function isFeed(item) { return item.type === 'feed'; }
    function source(item) { return isFeed(item) ? Feeds : YT; }

    function sectionOf(item) {
        for (var i = 0; i < sections.length; i++) {
            for (var j = 0; j < sections[i].items.length; j++) { if (sections[i].items[j] === item) { return sections[i]; } }
        }
        return null;
    }

    function findItem(key) {
        for (var i = 0; i < sections.length; i++) {
            for (var j = 0; j < sections[i].items.length; j++) {
                if (itemKey(sections[i].items[j]) === key) { return sections[i].items[j]; }
            }
        }
        return null;
    }

    function sectionsForTab(tab) {
        var out = [];
        for (var i = 0; i < sections.length; i++) { if ((sections[i].tab || sections[i].title) === tab) { out.push(sections[i]); } }
        return out;
    }

    function itemsOf(list) {
        var out = [];
        for (var i = 0; i < list.length; i++) { out = out.concat(list[i].items); }
        return out;
    }

    /* favourites & continue */

    function readJSON(key, fallback) {
        try { var v = JSON.parse(localStorage.getItem(key)); return v || fallback; } catch (e) { return fallback; }
    }
    function writeJSON(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* ignore */ } }

    function favourites() { return readJSON('favourites', []); }
    function isFavourite(item) { return favourites().indexOf(itemKey(item)) >= 0; }
    function toggleFavourite(item) {
        var list = favourites();
        var i = list.indexOf(itemKey(item));
        if (i >= 0) { list.splice(i, 1); toast('Removed from favourites'); } else { list.unshift(itemKey(item)); toast('Added to favourites'); }
        writeJSON('favourites', list);
    }
    function favouriteItems() {
        var out = [], keys = favourites();
        for (var i = 0; i < keys.length; i++) { var it = findItem(keys[i]); if (it) { out.push(it); } }
        return out;
    }

    function savedPos(ep) {
        try { return parseInt(localStorage.getItem('pos:' + ep.id), 10) || 0; } catch (e) { return 0; }
    }

    /* episode loading (shared cache, a few at a time) */

    var episodesByKey = {};
    var queue = [], queued = {}, running = 0, onLoaded = null;

    function want(items) {
        for (var i = 0; i < items.length; i++) {
            var k = itemKey(items[i]);
            if (!episodesByKey[k] && !queued[k]) { queued[k] = true; queue.push(items[i]); }
        }
        pump();
    }

    function pump() {
        while (running < LOAD_AT_ONCE && queue.length) {
            (function (item) {
                running++;
                source(item).loadEpisodes(item, function (err, episodes) {
                    running--;
                    episodesByKey[itemKey(item)] = err ? [] : episodes;
                    if (onLoaded) { onLoaded(); }
                    pump();
                });
            })(queue.shift());
        }
    }

    function latestFrom(items, count) {
        var out = [];
        for (var i = 0; i < items.length; i++) {
            var eps = episodesByKey[itemKey(items[i])];
            if (eps && eps.length) { out.push({ item: items[i], ep: eps[0] }); }
        }
        out.sort(function (a, b) { return time(b.ep.published) - time(a.ep.published); });
        return out.slice(0, count);
    }

    /* ---------- formatting ---------- */

    function time(iso) { var t = new Date(iso).getTime(); return isNaN(t) ? 0 : t; }

    function ago(iso) {
        var t = time(iso);
        if (!t) { return ''; }
        var days = Math.floor((Date.now() - t) / 86400000);
        if (days <= 0) { return 'Today'; }
        if (days === 1) { return 'Yesterday'; }
        if (days < 7) { return days + ' days ago'; }
        var d = new Date(t);
        return d.getDate() + ' ' + MONTHS[d.getMonth()] + (d.getFullYear() !== new Date().getFullYear() ? ' ' + d.getFullYear() : '');
    }

    function isNew(iso) { return Date.now() - time(iso) < 2 * 86400000; }

    function length(seconds) {
        if (!seconds) { return ''; }
        var m = Math.round(seconds / 60);
        return m < 60 ? m + ' min' : Math.floor(m / 60) + ' h ' + (m % 60) + ' min';
    }

    function summary(ep, item) {
        var text = (ep && ep.description) || '';
        // First paragraph, without links and hashtags.
        text = text.split(/\n\s*\n/)[0].replace(/https?:\/\/\S+/g, '').replace(/#\w+/g, '').replace(/\s+/g, ' ').replace(/^\s+|\s+$/g, '');
        return text || item.note || '';
    }

    function initials(title) {
        var words = title.replace(/^the\s+/i, '').split(/\s+/), out = '';
        for (var i = 0; i < words.length && out.length < 2; i++) { if (words[i]) { out += words[i].charAt(0).toUpperCase(); } }
        return out;
    }

    function hue(title) {
        var h = 0;
        for (var i = 0; i < title.length; i++) { h = (h * 31 + title.charCodeAt(i)) % 360; }
        return h;
    }

    function img(src, className, fallback) {
        var node = el('img', className);
        node.alt = '';
        node.onerror = function () {
            if (fallback && node.src.indexOf(fallback) < 0) { node.src = fallback; } else { node.style.visibility = 'hidden'; }
        };
        if (src) { node.src = src; } else { node.style.visibility = 'hidden'; }
        return node;
    }

    /* ---------- backdrop ---------- */

    var backdropSrc = '';
    function setBackdrop(src, soft) {
        $('backdrop').className = soft ? 'soft' : '';
        if (src === backdropSrc) { return; }
        backdropSrc = src;
        var node = $('backdrop-img');
        node.className = '';
        if (!src) { node.removeAttribute('src'); return; }
        var fallback = src.replace('maxresdefault', 'hqdefault');
        node.onload = function () { node.className = 'ready'; };
        node.onerror = function () { if (node.src !== fallback && src !== fallback) { node.src = fallback; } };
        node.src = src;
    }

    function backdropFor(item, ep) {
        if (ep && ep.backdrop) { return { src: ep.backdrop, soft: false }; }
        if (ep && ep.thumb) { return { src: ep.thumb, soft: false }; }
        return { src: item.image || '', soft: true };
    }

    /* ---------- cards ---------- */

    function episodeCard(item, ep, opts) {
        opts = opts || {};
        var card = el('div', 'ep');
        var thumb = el('div', 'thumb');
        if (ep.thumb) {
            thumb.appendChild(img(ep.thumb, 'pic', item.image));
        } else {
            thumb.className = 'thumb logo';
            thumb.appendChild(img(item.image, 'pic'));
            thumb.appendChild(img(item.image, 'center'));
        }
        if (opts.isNew && isNew(ep.published)) { thumb.appendChild(el('span', 'new', 'NEW')); }
        if (opts.badge) {
            var badge = el('span', 'badge');
            badge.appendChild(img(item.image));
            badge.appendChild(document.createTextNode(item.title));
            thumb.appendChild(badge);
        }
        if (ep.duration) { thumb.appendChild(el('span', 'dur', length(ep.duration))); }
        var pos = opts.pos || savedPos(ep);
        var dur = opts.duration || ep.duration;
        if (pos && dur) {
            var bar = el('div', 'progress'), fill = el('i');
            fill.style.width = Math.min(100, Math.round(pos / dur * 100)) + '%';
            bar.appendChild(fill);
            thumb.appendChild(bar);
        }
        card.appendChild(thumb);
        card.appendChild(el('div', 'ep-title', ep.title));
        var meta = opts.metaText || ago(ep.published);
        if (pos && dur) { meta += (meta ? ' · ' : '') + length(dur - pos) + ' left'; }
        card.appendChild(el('div', 'ep-meta', meta));
        return card;
    }

    function showCard(item) {
        var card = el('div', 'show');
        var disc = el('div', 'disc');
        var h = hue(item.title);
        disc.style.background = 'linear-gradient(135deg, hsl(' + h + ',55%,42%), hsl(' + ((h + 40) % 360) + ',60%,24%))';
        disc.appendChild(document.createTextNode(initials(item.title)));
        if (item.image) { disc.appendChild(img(item.image)); }
        card.appendChild(disc);
        if (isFavourite(item)) { card.appendChild(el('span', 'fav-dot', '♥')); }
        card.appendChild(el('div', 'name', item.title));
        return card;
    }

    /* ---------- home & tabs ---------- */

    var screen = 'home';
    var home = { tab: 0, zone: 'hero', heroBtn: 0, row: 0, cols: {}, rows: [], hero: null, tabFocus: 0 };
    var renderTimer = null;

    function buildTabs() {
        var bar = $('tabs');
        bar.innerHTML = '';
        for (var i = 0; i < tabs.length; i++) { bar.appendChild(el('div', 'tab', tabs[i])); }
    }

    function renderTabs() {
        var nodes = $('tabs').children;
        for (var i = 0; i < nodes.length; i++) {
            var cls = 'tab';
            if (i === home.tab) { cls += ' on'; }
            if (screen === 'home' && home.zone === 'tabs' && i === home.tabFocus) { cls += ' focus'; }
            nodes[i].className = cls;
        }
    }

    // What the current tab shows: featured episode + rows.
    function pageModel() {
        var tab = tabs[home.tab];
        var scope = tab === 'Home' ? itemsOf(sections) : itemsOf(sectionsForTab(tab));
        // Home pulls from YouTube channels (quick to load); large podcast feeds load on their own tab.
        var pool = [];
        for (var i = 0; i < scope.length; i++) { if (tab !== 'Home' || !isFeed(scope[i])) { pool.push(scope[i]); } }
        var favs = tab === 'Home' ? favouriteItems() : [];
        want(favs.concat(pool));

        var latest = latestFrom(favs.concat(pool), 20);
        var rows = [];

        if (tab === 'Home') {
            var cont = readJSON('continue', []), entries = [];
            for (var c = 0; c < cont.length; c++) {
                var it = findItem(cont[c].item.type + ':' + (cont[c].item.id || cont[c].item.url)) || cont[c].item;
                entries.push({ item: it, ep: cont[c].episode, pos: cont[c].pos, duration: cont[c].duration });
            }
            if (entries.length) { rows.push({ kind: 'eps', title: 'Continue watching', entries: entries, badge: true }); }
        }
        rows.push({ kind: 'eps', title: tab === 'Home' ? 'New from your shows' : 'Latest in ' + tab,
            sub: latest.length ? '' : 'Loading…', entries: latest.slice(1), badge: true, isNew: true });
        if (tab === 'Home' && favs.length) { rows.push({ kind: 'shows', title: 'Your favourites', items: favs }); }
        var list = tab === 'Home' ? sections : sectionsForTab(tab);
        for (var r = 0; r < list.length; r++) { rows.push({ kind: 'shows', title: list[r].title, items: list[r].items }); }

        // Drop empty episode rows (except the latest row while it loads).
        var kept = [];
        for (var k = 0; k < rows.length; k++) {
            if (rows[k].kind === 'shows' || rows[k].entries.length || rows[k].sub) { kept.push(rows[k]); }
        }
        return { hero: latest[0] || null, rows: kept };
    }

    function renderHome() {
        var model = pageModel();
        home.hero = model.hero;
        home.rows = model.rows;
        if (home.zone === 'hero' && !home.hero) { home.zone = 'rows'; home.row = 0; }
        // Until the viewer presses a key, keep the featured episode selected as soon as it exists.
        if (!home.touched && home.hero) { home.zone = 'hero'; home.heroBtn = 0; }
        if (home.row >= home.rows.length) { home.row = home.rows.length - 1; }

        var page = $('page');
        page.innerHTML = '';
        page.appendChild(buildHero(model.hero));
        for (var r = 0; r < home.rows.length; r++) { page.appendChild(buildRow(home.rows[r], r)); }
        focusHome();
    }

    function buildHero(entry) {
        var hero = el('div', 'hero');
        if (!entry) {
            hero.appendChild(el('div', 'kicker', tabs[home.tab] === 'Home' ? 'Watchlist' : tabs[home.tab]));
            hero.appendChild(el('h1', '', 'Finding the newest episodes…'));
            hero.appendChild(el('div', 'desc', 'Pick a show below in the meantime.'));
            setBackdrop('', false);
            return hero;
        }
        var kicker = el('div', 'kicker');
        kicker.appendChild(img(entry.item.image));
        kicker.appendChild(document.createTextNode((isNew(entry.ep.published) ? 'New episode · ' : 'Latest · ') + entry.item.title));
        hero.appendChild(kicker);
        hero.appendChild(el('h1', '', entry.ep.title));
        var meta = el('div', 'meta');
        if (isNew(entry.ep.published)) { meta.appendChild(el('span', 'chip red', 'NEW')); }
        meta.appendChild(el('span', '', ago(entry.ep.published)));
        var section = sectionOf(entry.item);
        if (section) { meta.appendChild(el('span', '', '·')); meta.appendChild(el('span', '', section.title)); }
        if (entry.ep.duration) { meta.appendChild(el('span', '', '·')); meta.appendChild(el('span', '', length(entry.ep.duration))); }
        hero.appendChild(meta);
        hero.appendChild(el('div', 'desc', summary(entry.ep, entry.item)));
        var btns = el('div', 'btns');
        var play = el('div', 'btn primary');
        play.appendChild(el('span', 'play-icon'));
        play.appendChild(document.createTextNode(isFeed(entry.item) ? 'Play now' : 'Watch now'));
        btns.appendChild(play);
        btns.appendChild(el('div', 'btn', 'All episodes'));
        hero.appendChild(btns);
        var bd = backdropFor(entry.item, entry.ep);
        setBackdrop(bd.src, bd.soft);
        return hero;
    }

    function buildRow(row, index) {
        var node = el('div', 'row');
        var title = el('div', 'rowtitle', row.title);
        if (row.sub) { title.appendChild(el('small', '', row.sub)); }
        node.appendChild(title);
        var clip = el('div', 'clip'), track = el('div', 'track');
        if (row.kind === 'eps') {
            for (var i = 0; i < row.entries.length; i++) {
                var e = row.entries[i];
                track.appendChild(episodeCard(e.item, e.ep, { badge: row.badge, isNew: row.isNew, pos: e.pos, duration: e.duration }));
            }
        } else {
            for (var j = 0; j < row.items.length; j++) { track.appendChild(showCard(row.items[j])); }
        }
        clip.appendChild(track);
        node.appendChild(clip);
        return node;
    }

    function rowLength(row) { return row.kind === 'eps' ? row.entries.length : row.items.length; }
    function colOf(r) { return home.cols[tabs[home.tab] + ':' + r] || 0; }
    function setCol(r, c) { home.cols[tabs[home.tab] + ':' + r] = c; }

    function focusHome() {
        renderTabs();
        var page = $('page');
        var heroNode = page.children[0];
        var btns = heroNode.getElementsByClassName('btn');
        for (var b = 0; b < btns.length; b++) {
            btns[b].className = btns[b].className.replace(' focus', '') + (home.zone === 'hero' && b === home.heroBtn ? ' focus' : '');
        }
        for (var r = 0; r < home.rows.length; r++) {
            var rowNode = page.children[r + 1];
            var active = home.zone === 'rows' && r === home.row;
            rowNode.className = active ? 'row active' : 'row';
            var track = rowNode.getElementsByClassName('track')[0];
            var cards = track.children, col = colOf(r);
            if (col >= cards.length) { col = Math.max(0, cards.length - 1); setCol(r, col); }
            for (var c = 0; c < cards.length; c++) {
                var base = home.rows[r].kind === 'eps' ? 'ep' : 'show';
                cards[c].className = base + (active && c === col ? ' focus' : '');
            }
            var shift = home.rows[r].kind === 'eps' ? Math.max(0, col - 2) * EP_STEP : Math.max(0, col - 6) * SHOW_STEP;
            setTransform(track, 'translateX(' + -shift + 'px)');
        }
        // Vertical scroll: the first row sits under the featured episode; later rows scroll up under the top bar.
        var offset = 0;
        if (home.zone === 'rows' && home.row > 0) { offset = page.children[home.row + 1].offsetTop - 140; }
        setTransform(page, 'translateY(' + -offset + 'px)');
        $('backdrop').className = $('backdrop').className.replace(' dim', '') + (offset > 0 ? ' dim' : '');
        $('topbar').className = offset > 0 ? 'solid' : '';
    }

    function homeKey(code) {
        home.touched = true;
        if (home.zone === 'tabs') {
            if (code === KEY.LEFT && home.tabFocus > 0) { home.tabFocus--; switchTab(home.tabFocus); }
            else if (code === KEY.RIGHT && home.tabFocus < tabs.length - 1) { home.tabFocus++; switchTab(home.tabFocus); }
            else if (code === KEY.DOWN || code === KEY.ENTER) { home.zone = home.hero ? 'hero' : 'rows'; home.row = 0; focusHome(); }
            return;
        }
        if (home.zone === 'hero') {
            if (code === KEY.LEFT && home.heroBtn > 0) { home.heroBtn--; }
            else if (code === KEY.RIGHT && home.heroBtn < 1) { home.heroBtn++; }
            else if (code === KEY.UP) { home.zone = 'tabs'; home.tabFocus = home.tab; }
            else if (code === KEY.DOWN && home.rows.length) { home.zone = 'rows'; home.row = 0; }
            else if (code === KEY.ENTER && home.hero) {
                if (home.heroBtn === 0) { playEpisode(home.hero.item, home.hero.ep); } else { openDetail(home.hero.item); }
                return;
            }
            focusHome();
            return;
        }
        var row = home.rows[home.row], col = colOf(home.row), n = rowLength(row);
        if (code === KEY.LEFT && col > 0) { setCol(home.row, col - 1); }
        else if (code === KEY.RIGHT && col < n - 1) { setCol(home.row, col + 1); }
        else if (code === KEY.UP) {
            if (home.row > 0) { home.row--; } else if (home.hero) { home.zone = 'hero'; } else { home.zone = 'tabs'; home.tabFocus = home.tab; }
        }
        else if (code === KEY.DOWN && home.row < home.rows.length - 1) { home.row++; }
        else if (code === KEY.ENTER && n) {
            if (row.kind === 'eps') { var e = row.entries[col]; playEpisode(e.item, e.ep); }
            else { openDetail(row.items[col]); }
            return;
        }
        focusHome();
    }

    function switchTab(index) {
        home.tab = index;
        home.row = 0;
        home.heroBtn = 0;
        renderHome();
    }

    // Re-draw as episodes arrive, but not more than every 1.5 s, and only on the home screen.
    onLoaded = function () {
        if (renderTimer) { return; }
        renderTimer = setTimeout(function () {
            renderTimer = null;
            if (screen === 'home') { renderHome(); }
            else if (screen === 'detail') { refreshDetailIfWaiting(); }
        }, 1500);
    };

    /* ---------- show page ---------- */

    var detail = { item: null, episodes: [], zone: 'btns', btn: 0, focus: 0, token: 0, waiting: false };

    function detailButtons() {
        var list = [{ id: 'play', label: 'Play latest episode', primary: true }];
        if (!isFeed(detail.item)) { list.push({ id: 'yt', label: 'Open channel in YouTube' }); }
        list.push({ id: 'fav', label: isFavourite(detail.item) ? '♥' : '♡', round: true, on: isFavourite(detail.item) });
        return list;
    }

    function openDetail(item) {
        detail.item = item;
        detail.episodes = [];
        detail.zone = 'btns';
        detail.btn = 0;
        detail.focus = 0;
        var token = ++detail.token;

        var section = sectionOf(item);
        $('detail-logo').src = item.image || '';
        $('detail-logo').style.visibility = item.image ? 'visible' : 'hidden';
        $('detail-title').textContent = item.title;
        var meta = $('detail-meta');
        meta.innerHTML = '';
        meta.appendChild(el('span', 'chip', isFeed(item) ? 'INDEPENDENT' : (section ? section.title.toUpperCase() : 'SHOW')));
        meta.appendChild(el('span', '', isFeed(item) ? 'Plays in Watchlist' : 'Opens in YouTube'));
        $('detail-note').textContent = item.note || '';
        $('detail-count').textContent = '';
        $('grid').innerHTML = '';
        $('status').textContent = 'Loading episodes…';
        $('status').className = '';

        screen = 'detail';
        $('home').className = 'screen hidden';
        $('detail').className = 'screen';
        $('back-hint').className = '';
        $('tabs').className = 'hidden';
        $('topbar').className = '';
        setBackdrop(item.image || '', true);
        renderDetail();

        var cached = episodesByKey[itemKey(item)];
        if (cached && cached.length) { showEpisodes(cached); return; }
        detail.waiting = true;
        source(item).loadEpisodes(item, function (err, episodes) {
            if (token !== detail.token) { return; }
            detail.waiting = false;
            if (!err) { episodesByKey[itemKey(item)] = episodes; }
            if (err === 'not-found' && !isFeed(item)) {
                $('status').textContent = 'YouTube has no ' + item.type + ' with the ID "' + item.id + '". Check it in js/collection.js.';
            } else if (err) {
                $('status').textContent = 'Could not load episodes. Check the TV\'s internet connection and try again.';
            } else if (!episodes.length) {
                $('status').textContent = 'No episodes yet.';
            } else {
                showEpisodes(episodes);
            }
        });
    }

    function refreshDetailIfWaiting() { /* the detail screen loads its own list; nothing to do */ }

    function showEpisodes(episodes) {
        detail.episodes = episodes;
        $('status').className = 'hidden';
        $('detail-count').textContent = episodes.length + ' episodes';
        var meta = $('detail-meta');
        meta.appendChild(el('span', '', '·'));
        meta.appendChild(el('span', '', 'Latest ' + ago(episodes[0].published).toLowerCase()));
        if (!detail.item.note) { $('detail-note').textContent = summary(episodes[0], detail.item); }
        var grid = $('grid');
        grid.innerHTML = '';
        for (var i = 0; i < episodes.length; i++) { grid.appendChild(episodeCard(detail.item, episodes[i], { isNew: true })); }
        var bd = backdropFor(detail.item, episodes[0]);
        setBackdrop(bd.src, bd.soft);
        renderDetail();
    }

    function renderDetail() {
        var list = detailButtons(), box = $('detail-btns');
        box.innerHTML = '';
        for (var b = 0; b < list.length; b++) {
            var btn = el('div', 'btn' + (list[b].primary ? ' primary' : '') + (list[b].round ? ' round' : '') + (list[b].on ? ' on' : '') +
                (detail.zone === 'btns' && b === detail.btn ? ' focus' : ''));
            if (list[b].primary) { btn.appendChild(el('span', 'play-icon')); }
            btn.appendChild(document.createTextNode(list[b].label));
            box.appendChild(btn);
        }
        var cards = $('grid').children;
        for (var i = 0; i < cards.length; i++) { cards[i].className = 'ep' + (detail.zone === 'eps' && i === detail.focus ? ' focus' : ''); }
        setTransform($('grid'), 'translateX(' + -(Math.max(0, detail.focus - 2) * EP_STEP) + 'px)');
        $('detail-row').className = detail.zone === 'eps' ? 'row active' : 'row';
    }

    function detailKey(code) {
        var list = detailButtons();
        if (detail.zone === 'btns') {
            if (code === KEY.LEFT && detail.btn > 0) { detail.btn--; }
            else if (code === KEY.RIGHT && detail.btn < list.length - 1) { detail.btn++; }
            else if (code === KEY.DOWN && detail.episodes.length) { detail.zone = 'eps'; }
            else if (code === KEY.ENTER) {
                var id = list[detail.btn].id;
                if (id === 'play') {
                    if (detail.episodes.length) { playEpisode(detail.item, detail.episodes[0]); } else { toast('Episodes are still loading…'); }
                } else if (id === 'yt') {
                    toast('Opening ' + detail.item.title + ' in YouTube…');
                    YT.openItem(detail.item, launched);
                } else if (id === 'fav') {
                    toggleFavourite(detail.item);
                }
            }
        } else {
            if (code === KEY.LEFT && detail.focus > 0) { detail.focus--; }
            else if (code === KEY.RIGHT && detail.focus < detail.episodes.length - 1) { detail.focus++; }
            else if (code === KEY.UP) { detail.zone = 'btns'; }
            else if (code === KEY.ENTER) { playEpisode(detail.item, detail.episodes[detail.focus]); return; }
        }
        renderDetail();
    }

    function closeDetail() {
        detail.token++;
        screen = 'home';
        $('detail').className = 'screen hidden';
        $('home').className = 'screen';
        $('back-hint').className = 'hidden';
        $('tabs').className = '';
        renderHome();
    }

    /* ---------- playing ---------- */

    function launched(err, method) {
        if (err) { toast('Could not open YouTube. Is the YouTube app installed on this TV?'); return; }
        try { localStorage.setItem('yt:lastMethod', method || ''); } catch (e) { /* ignore */ }
    }

    function playEpisode(item, ep) {
        if (!isFeed(item)) {
            toast('Opening in YouTube…');
            YT.openVideo(ep.id, launched);
            return;
        }
        var back = screen;
        screen = 'player';
        Player.open(ep, item, function (reason) {
            screen = back;
            if (back === 'detail') { renderDetailCards(); renderDetail(); } else { renderHome(); }
            if (reason === 'error') { toast('This episode could not be played on this TV.'); }
        });
    }

    // Refresh progress bars after leaving the player.
    function renderDetailCards() {
        var grid = $('grid');
        grid.innerHTML = '';
        for (var i = 0; i < detail.episodes.length; i++) { grid.appendChild(episodeCard(detail.item, detail.episodes[i], { isNew: true })); }
    }

    /* ---------- shared ---------- */

    var toastTimer = null;
    function toast(message) {
        var node = $('toast');
        node.textContent = message;
        node.className = '';
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () { node.className = 'hidden'; }, 3500);
    }

    function tick() {
        var d = new Date(), m = d.getMinutes();
        $('clock').textContent = d.getHours() + ':' + (m < 10 ? '0' + m : m);
    }

    function exitApp() {
        try { tizen.application.getCurrentApplication().exit(); } catch (e) { /* not on a TV */ }
    }

    document.addEventListener('keydown', function (e) {
        var code = e.keyCode;
        if (screen === 'player') { e.preventDefault(); Player.key(code); return; }
        if (code === KEY.BACK || code === KEY.ESC || code === KEY.BACKSPACE) {
            e.preventDefault();
            if (screen === 'detail') { closeDetail(); }
            else if (home.zone !== 'tabs') { home.zone = 'tabs'; home.tabFocus = home.tab; focusHome(); }
            else { exitApp(); }
            return;
        }
        if (code >= KEY.LEFT && code <= KEY.DOWN) { e.preventDefault(); }
        if (screen === 'home') { homeKey(code); } else if (screen === 'detail') { detailKey(code); }
    });

    buildTabs();
    renderHome();
    tick();
    setInterval(tick, 15000);
})();
