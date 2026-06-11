/* ── Morning Dashboard — app.js ──────────────────────────────────── */

const ALL_TABS = ['spurgeon','news','weather','bible','prayer','notes','sermons'];

const TAB_META = {
    spurgeon: { emoji: '📖', label: 'Devotional', accent: '#f0a500' },
    news:     { emoji: '📰', label: 'News',       accent: '#4a9eff' },
    weather:  { emoji: '🌤️', label: 'Weather',    accent: '#00bcd4' },
    sermons:  { emoji: '✍️', label: 'Sermons',    accent: '#66bb6a' },
    bible:    { emoji: '📜', label: 'Bible',      accent: '#ffd54f' },
    prayer:   { emoji: '🙏', label: 'Prayer',     accent: '#ef5350' },
    notes:    { emoji: '📝', label: 'Notes',      accent: '#ff7043' },
};

const BIBLE_BOOKS = [
    ['Genesis','GEN',50],['Exodus','EXO',40],['Leviticus','LEV',27],
    ['Numbers','NUM',36],['Deuteronomy','DEU',34],['Joshua','JOS',24],
    ['Judges','JDG',21],['Ruth','RUT',4],['1 Samuel','1SA',31],
    ['2 Samuel','2SA',24],['1 Kings','1KI',22],['2 Kings','2KI',25],
    ['1 Chronicles','1CH',29],['2 Chronicles','2CH',36],['Ezra','EZR',10],
    ['Nehemiah','NEH',13],['Esther','EST',10],['Job','JOB',42],
    ['Psalms','PSA',150],['Proverbs','PRO',31],['Ecclesiastes','ECC',12],
    ['Song of Solomon','SNG',8],['Isaiah','ISA',66],['Jeremiah','JER',52],
    ['Lamentations','LAM',5],['Ezekiel','EZK',48],['Daniel','DAN',12],
    ['Hosea','HOS',14],['Joel','JOL',3],['Amos','AMO',9],
    ['Obadiah','OBA',1],['Jonah','JON',4],['Micah','MIC',7],
    ['Nahum','NAH',3],['Habakkuk','HAB',3],['Zephaniah','ZEP',3],
    ['Haggai','HAG',2],['Zechariah','ZEC',14],['Malachi','MAL',4],
    ['Matthew','MAT',28],['Mark','MRK',16],['Luke','LUK',24],
    ['John','JHN',21],['Acts','ACT',28],['Romans','ROM',16],
    ['1 Corinthians','1CO',16],['2 Corinthians','2CO',13],
    ['Galatians','GAL',6],['Ephesians','EPH',6],['Philippians','PHP',4],
    ['Colossians','COL',4],['1 Thessalonians','1TH',5],['2 Thessalonians','2TH',3],
    ['1 Timothy','1TI',6],['2 Timothy','2TI',4],['Titus','TIT',3],
    ['Philemon','PHM',1],['Hebrews','HEB',13],['James','JAS',5],
    ['1 Peter','1PE',5],['2 Peter','2PE',3],['1 John','1JN',5],
    ['2 John','2JN',1],['3 John','3JN',1],['Jude','JUD',1],
    ['Revelation','REV',22],
];

const BIBLE_TRANSLATIONS = [
    ['World English Bible','web'],
    ['King James Version','kjv'],
    ['American Standard Version','asv'],
    ['Bible in Basic English','bbe'],
    ['Darby Bible','darby'],
    ["Young's Literal Translation","ylt"],
    ['Open English Bible (US)','oeb-us'],
    ['Open English Bible (UK)','oeb-cw'],
    ['World English Bible (British)','webbe'],
    ['Douay-Rheims 1899','dra'],
    ['CSB (API.Bible)','apibible:CSB'],
    ['NLT (API.Bible)','apibible:NLT'],
    ['NIV (API.Bible)','apibible:NIV'],
];

/* ── State ─────────────────────────────────────────────────────────── */
let prefs = window.INIT_PREFS;
let activeTab = null;
const tabLoaded = {};

// Spurgeon state
let spurgeonDate = new Date();
spurgeonDate.setHours(0,0,0,0);
let spurgeonNotesTimer = null;
let spurgeonNotesLoading = false;

// Bible state
let bibleState = { bookIdx: 0, chapter: 1, translation: 'web' };

// Prayer state
let prayerData = [];

// Notes state
let notesTimer = null;

// Sermons state
let currentSermonFile = null;

/* ── Helpers ───────────────────────────────────────────────────────── */
function dateToISO(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth()+1).padStart(2,'0');
    const day = String(d.getDate()).padStart(2,'0');
    return `${y}-${m}-${day}`;
}

function formatDateFull(d) {
    return d.toLocaleDateString('en-GB', { weekday:'long', day:'2-digit', month:'long', year:'numeric' });
}

async function api(endpoint, opts={}, timeoutMs=20000) {
    const headers = {'X-Requested-With': 'XMLHttpRequest', ...(opts.headers||{})};
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    let res;
    try {
        res = await fetch('api/' + endpoint, {...opts, headers, signal: controller.signal});
    } catch (e) {
        if (e.name === 'AbortError') throw new Error('Request timed out');
        throw e;
    } finally {
        clearTimeout(timer);
    }
    if (res.status === 401) { window.location.href = '/login.php'; return; }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

function el(tag, attrs={}, ...children) {
    const e = document.createElement(tag);
    for (const [k,v] of Object.entries(attrs)) {
        if (k === 'class') e.className = v;
        else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
        else e.setAttribute(k, v);
    }
    for (const c of children) {
        if (c == null) continue;
        e.append(typeof c === 'string' ? document.createTextNode(c) : c);
    }
    return e;
}

/* ── Init ──────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
    applyTheme();

    // Date label
    document.getElementById('date-label').textContent = formatDateFull(new Date());

    buildSidebar();

    // Settings button
    document.getElementById('settings-btn').addEventListener('click', openSettings);
    document.getElementById('close-settings-btn').addEventListener('click', closeSettings);
    document.getElementById('cancel-settings-btn').addEventListener('click', closeSettings);
    document.getElementById('save-settings-btn').addEventListener('click', saveSettings);
    document.getElementById('settings-modal').addEventListener('click', e => {
        if (e.target === e.currentTarget) closeSettings();
    });

    // Collapse button
    document.getElementById('collapse-btn').addEventListener('click', toggleSidebar);

    // Logout button
    document.getElementById('logout-btn').addEventListener('click', () => {
        api('logout.php', {method: 'POST'}).then(() => { location.href = '/login.php'; });
    });

    // Switch to first visible tab
    const firstTab = prefs.tab_order.find(k => prefs.visible_tabs.includes(k));
    if (firstTab) switchTab(firstTab);
});

/* ── Theme ─────────────────────────────────────────────────────────── */
function applyTheme() {
    document.documentElement.setAttribute('data-theme', prefs.theme);
    document.documentElement.style.setProperty('--font-size', prefs.font_size + 'px');
}

/* ── Sidebar ───────────────────────────────────────────────────────── */
function buildSidebar() {
    const iconCol  = document.getElementById('icon-col');
    const labelCol = document.getElementById('label-col');
    const spacer   = iconCol.querySelector('.sidebar-spacer');
    const lSpacer  = labelCol.querySelector('.sidebar-spacer');

    iconCol.querySelectorAll('.icon-row').forEach(e => e.remove());
    labelCol.querySelectorAll('.sidebar-label-btn').forEach(e => e.remove());

    const order = prefs.tab_order.filter(k => prefs.visible_tabs.includes(k));
    for (const key of order) {
        const meta = TAB_META[key];
        if (!meta) continue;

        const indicator = el('div', { class: `sidebar-indicator sidebar-indicator-${key}` });
        const iconBtn   = el('button', { class: 'sidebar-icon-btn', title: meta.label,
                                          onclick: () => switchTab(key) }, meta.emoji);
        const iconRow   = el('div', { class: 'icon-row', 'data-tab': key }, indicator, iconBtn);
        iconCol.insertBefore(iconRow, spacer);

        const labelBtn = el('button', { class: 'sidebar-label-btn', 'data-tab': key,
                                         onclick: () => switchTab(key) }, meta.label);
        labelCol.insertBefore(labelBtn, lSpacer);
    }
}

function switchTab(key) {
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.icon-row').forEach(r => r.classList.toggle('active', r.dataset.tab === key));
    document.querySelectorAll('.sidebar-label-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === key));

    const panel = document.getElementById('tab-' + key);
    if (panel) panel.classList.add('active');
    activeTab = key;

    if (!tabLoaded[key]) {
        tabLoaded[key] = true;
        loadTab(key);
    }
}

function loadTab(key) {
    switch (key) {
        case 'spurgeon': initSpurgeon(); break;
        case 'news':     initNews();     break;
        case 'weather':  initWeather();  break;
        case 'bible':    initBible();    break;
        case 'prayer':   initPrayer();   break;
        case 'notes':    initNotes();    break;
        case 'sermons':  initSermons();  break;
    }
}

function toggleSidebar() {
    prefs.sidebar_collapsed = !prefs.sidebar_collapsed;
    const labelCol  = document.getElementById('label-col');
    const collapseBtn = document.getElementById('collapse-btn');
    labelCol.classList.toggle('hidden', prefs.sidebar_collapsed);
    collapseBtn.textContent = prefs.sidebar_collapsed ? '▶' : '◀';
    savePrefsSilent();
}

/* ── SPURGEON TAB ──────────────────────────────────────────────────── */
function initSpurgeon() {
    const panel = document.getElementById('tab-spurgeon');
    panel.innerHTML = `
    <div class="spurgeon-paned">
      <div class="spurgeon-left">
        <div class="sermon-toolbar">
          <button class="sermon-btn" id="spur-prev">◀ Prev</button>
          <span class="section-title flex-1" style="text-align:center" id="spur-date-lbl"></span>
          <button class="sermon-btn" id="spur-next">Next ▶</button>
          <button class="sermon-btn" id="spur-today">Today</button>
        </div>
        <div class="spurgeon-reading-scroll">
          <div id="spurgeon-reading"><span class="status-label">Loading today's reading…</span></div>
        </div>
      </div>
      <div class="spurgeon-right">
        <div class="spurgeon-notes-header">
          <span class="section-title" id="spur-notes-date-lbl">Notes</span>
          <button class="sermon-btn" id="spur-export-btn">Export all…</button>
        </div>
        <textarea id="spurgeon-notes" placeholder="Notes for today…"></textarea>
        <div class="spur-comments-section">
          <div class="spurgeon-notes-header">
            <span class="section-title">Community Comments</span>
          </div>
          <div id="spur-comments-list" class="spur-comments-list"></div>
          <div class="spur-comment-form">
            <textarea id="spur-comment-input" placeholder="Add a comment… (Ctrl+Enter to post)"></textarea>
            <button class="sermon-btn" id="spur-comment-submit">Post</button>
          </div>
        </div>
      </div>
    </div>`;

    document.getElementById('spur-prev').onclick  = () => spurgeonNav(-1);
    document.getElementById('spur-next').onclick  = () => spurgeonNav(+1);
    document.getElementById('spur-today').onclick = () => { spurgeonDate = new Date(); spurgeonDate.setHours(0,0,0,0); spurgeonRefresh(); };
    document.getElementById('spurgeon-notes').addEventListener('input', spurgeonNotesChanged);
    document.getElementById('spur-export-btn').onclick = exportSpurgeonNotes;
    document.getElementById('spur-comment-submit').onclick = postSpurgeonComment;
    document.getElementById('spur-comment-input').addEventListener('keydown', e => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) postSpurgeonComment();
    });

    spurgeonRefresh();
}

function spurgeonNav(delta) {
    spurgeonDate = new Date(spurgeonDate.getTime() + delta * 86400000);
    spurgeonRefresh();
}

function spurgeonRefresh() {
    const dateStr = formatDateFull(spurgeonDate);
    document.getElementById('spur-date-lbl').textContent = dateStr;
    document.getElementById('spur-notes-date-lbl').textContent = 'Notes — ' + dateStr;
    document.getElementById('spurgeon-reading').innerHTML = '<span class="status-label">Loading…</span>';
    loadSpurgeonReading();
    loadSpurgeonNotes();
    loadSpurgeonComments();
}

async function loadSpurgeonReading() {
    try {
        const data = await api('spurgeon.php?date=' + dateToISO(spurgeonDate));
        renderSpurgeonReading(data.readings || []);
    } catch(e) {
        document.getElementById('spurgeon-reading').textContent = 'Could not load reading: ' + e.message;
    }
}

function renderSpurgeonReading(readings) {
    const container = document.getElementById('spurgeon-reading');
    container.innerHTML = '';
    readings.forEach((r, i) => {
        if (i > 0) {
            const hr = document.createElement('hr');
            hr.className = 'divider';
            container.appendChild(hr);
        }
        const heading = el('span', { class: 'section-heading' }, r.label);
        container.appendChild(heading);

        const text = r.text || '';
        // Detect and linkify scripture references
        const html = linkifyScriptureRefs(escapeHtml(text));
        const body = document.createElement('div');
        body.innerHTML = html;
        // Attach click handlers to verse-ref links
        body.querySelectorAll('.verse-ref').forEach(link => {
            link.addEventListener('click', () => {
                const bookIdx = parseInt(link.dataset.bookIdx);
                const chapter  = parseInt(link.dataset.chapter);
                openBibleRef(bookIdx, chapter);
            });
        });
        container.appendChild(body);
    });
}

function escapeHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function linkifyScriptureRefs(text) {
    const bookNames = BIBLE_BOOKS.map(b => b[0]);
    const escaped = bookNames.map(n => n.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'));
    // Match "Book Chapter:verse" or "Book Chapter"
    const pattern = new RegExp(
        '((?:\\d+\\s+)?(?:' + escaped.join('|') + '))\\s+(\\d+)(?::\\d+[-\\d–]*)?',
        'gi'
    );
    return text.replace(pattern, (match, bookStr, chapterStr) => {
        const idx = findBookIndex(bookStr.trim());
        if (idx === -1) return match;
        const chapter = Math.min(parseInt(chapterStr), BIBLE_BOOKS[idx][2]);
        return `<span class="verse-ref" data-book-idx="${idx}" data-chapter="${chapter}">${match}</span>`;
    });
}

function findBookIndex(name) {
    const lower = name.toLowerCase();
    const aliases = { 'psalm': 'psalms', 'song of songs': 'song of solomon', 'song': 'song of solomon' };
    const resolved = aliases[lower] || lower;
    const exact = BIBLE_BOOKS.findIndex(b => b[0].toLowerCase() === resolved);
    if (exact !== -1) return exact;
    return BIBLE_BOOKS.findIndex(b => b[0].toLowerCase().startsWith(resolved) || resolved.startsWith(b[0].toLowerCase()));
}

async function loadSpurgeonNotes() {
    spurgeonNotesLoading = true;
    try {
        const data = await api('spurgeon_notes.php?date=' + dateToISO(spurgeonDate));
        const ta = document.getElementById('spurgeon-notes');
        if (ta) ta.value = data.text || '';
    } catch(e) {}
    spurgeonNotesLoading = false;
}

function spurgeonNotesChanged() {
    if (spurgeonNotesLoading) return;
    clearTimeout(spurgeonNotesTimer);
    spurgeonNotesTimer = setTimeout(saveSpurgeonNotes, 1000);
}

async function saveSpurgeonNotes() {
    const ta = document.getElementById('spurgeon-notes');
    if (!ta) return;
    try {
        await api('spurgeon_notes.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date: dateToISO(spurgeonDate), text: ta.value }),
        });
    } catch(e) {}
}

async function exportSpurgeonNotes() {
    try {
        const res = await fetch('api/spurgeon_notes.php?export=1');
        const blob = await res.blob();
        const url  = URL.createObjectURL(blob);
        const a    = document.createElement('a');
        a.href = url; a.download = 'spurgeon_notes.txt'; a.click();
        URL.revokeObjectURL(url);
    } catch(e) { alert('Export failed: ' + e.message); }
}

async function loadSpurgeonComments() {
    const list = document.getElementById('spur-comments-list');
    if (!list) return;
    list.innerHTML = '<span class="status-label">Loading…</span>';
    try {
        const data = await api('spurgeon_comments.php?date=' + dateToISO(spurgeonDate));
        renderSpurgeonComments(data.comments || []);
    } catch(e) {
        list.innerHTML = '<span class="status-label">Could not load comments</span>';
    }
}

function renderSpurgeonComments(comments) {
    const list = document.getElementById('spur-comments-list');
    if (!list) return;
    list.innerHTML = '';
    if (!comments.length) {
        list.appendChild(el('span', { class: 'status-label' }, 'No comments yet — be the first!'));
        return;
    }
    comments.forEach(c => {
        const canDelete = c.username === window.CURRENT_USER || window.IS_ADMIN;
        const ts = new Date(c.timestamp * 1000).toLocaleString('en-GB', {
            day: '2-digit', month: 'short', year: 'numeric',
            hour: '2-digit', minute: '2-digit',
        });
        const headerItems = [
            el('span', { class: 'spur-comment-user' }, c.username),
            el('span', { class: 'spur-comment-ts' }, ts),
        ];
        if (canDelete) {
            const delBtn = el('button', { class: 'spur-comment-del' }, '✕');
            delBtn.onclick = () => deleteSpurgeonComment(c.id);
            headerItems.push(delBtn);
        }
        list.appendChild(el('div', { class: 'spur-comment' },
            el('div', { class: 'spur-comment-header' }, ...headerItems),
            el('div', { class: 'spur-comment-body' }, c.text)
        ));
    });
}

async function postSpurgeonComment() {
    const input = document.getElementById('spur-comment-input');
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;
    try {
        await api('spurgeon_comments.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date: dateToISO(spurgeonDate), text }),
        });
        input.value = '';
        await loadSpurgeonComments();
    } catch(e) { alert('Could not post comment: ' + e.message); }
}

async function deleteSpurgeonComment(id) {
    if (!confirm('Delete this comment?')) return;
    try {
        await api('spurgeon_comments.php', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date: dateToISO(spurgeonDate), id }),
        });
        await loadSpurgeonComments();
    } catch(e) { alert('Could not delete comment: ' + e.message); }
}

function openBibleRef(bookIdx, chapter) {
    bibleState.bookIdx    = bookIdx;
    bibleState.chapter    = chapter;
    switchTab('bible');
    if (tabLoaded['bible']) {
        applyBibleState();
        loadBibleChapter();
    }
}

/* ── NEWS TAB ──────────────────────────────────────────────────────── */
function initNews() {
    const panel = document.getElementById('tab-news');
    panel.innerHTML = '<div class="tab-content"><span class="status-label">Loading news…</span></div>';
    api('news.php').then(data => renderNews(data)).catch(e => {
        panel.innerHTML = `<div class="tab-content"><span class="status-label">Could not load news: ${e.message}</span></div>`;
    });
}

function renderNews(data) {
    const panel = document.getElementById('tab-news');
    const box = el('div', { class: 'tab-content' });
    for (const [source, items] of Object.entries(data.sources || {})) {
        box.appendChild(el('span', { class: 'source-label' }, source.toUpperCase()));
        for (const [title, link] of items) {
            const btn = el('button', { class: 'news-button',
                onclick: () => link && /^https?:\/\//i.test(link) && window.open(link, '_blank', 'noopener') }, '  • ' + title);
            box.appendChild(btn);
        }
    }
    panel.innerHTML = '';
    panel.appendChild(box);
}

/* ── WEATHER TAB ───────────────────────────────────────────────────── */
function initWeather() {
    const panel = document.getElementById('tab-weather');
    panel.innerHTML = '<div class="tab-content"><span class="status-label">Loading weather…</span></div>';
    const params = new URLSearchParams();
    if (prefs.weather_lat) params.set('lat', prefs.weather_lat);
    if (prefs.weather_lon) params.set('lon', prefs.weather_lon);
    if (prefs.weather_location) params.set('location', prefs.weather_location);

    api('weather.php?' + params).then(data => renderWeather(data)).catch(e => {
        panel.innerHTML = `<div class="tab-content"><span class="status-label">Could not load weather: ${e.message}</span></div>`;
    });
}

function renderWeather(data) {
    const panel = document.getElementById('tab-weather');
    const box = el('div', { class: 'tab-content' });

    const current = el('div', { class: 'weather-current' },
        el('div', { class: 'weather-icon' }, data.icon || '🌡️'),
        el('div', { class: 'weather-temp' }, data.temp || '--°C'),
        el('div', { class: 'weather-desc' }, data.desc || ''),
    );
    box.appendChild(current);

    if (data.forecast && data.forecast.length) {
        box.appendChild(el('span', { class: 'source-label' }, '7-DAY FORECAST'));
        const grid = el('div', { class: 'forecast-grid' });
        for (const f of data.forecast) {
            grid.appendChild(el('div', { class: 'forecast-card' },
                el('div', { class: 'forecast-day'  }, f.day),
                el('div', { class: 'forecast-icon' }, f.icon),
                el('div', { class: 'forecast-hi'   }, f.hi),
                el('div', { class: 'forecast-lo'   }, f.lo),
            ));
        }
        box.appendChild(grid);
    }

    box.appendChild(el('div', { class: 'status-label', style: 'text-align:center;margin-top:12px' },
        'Weather powered by Open-Meteo (no API key needed)'));

    panel.innerHTML = '';
    panel.appendChild(box);
}

/* ── BIBLE TAB ─────────────────────────────────────────────────────── */
function initBible() {
    const panel = document.getElementById('tab-bible');

    // Book select
    const bookSel = el('select', { class: 'bible-select', id: 'bible-book-sel',
        onchange: () => { bibleState.bookIdx = parseInt(bookSel.value); bibleState.chapter = 1; chapInp.value = 1; chapInp.max = BIBLE_BOOKS[bibleState.bookIdx][2]; loadBibleChapter(); } });
    BIBLE_BOOKS.forEach(([name,,], i) => bookSel.appendChild(el('option', { value: i }, name)));
    bookSel.value = bibleState.bookIdx;

    // Chapter input
    const chapInp = el('input', { type: 'number', class: 'bible-chapter-input', id: 'bible-chap-inp',
        min: 1, max: BIBLE_BOOKS[bibleState.bookIdx][2], value: bibleState.chapter });
    chapInp.addEventListener('change', () => {
        let v = parseInt(chapInp.value) || 1;
        v = Math.max(1, Math.min(v, BIBLE_BOOKS[bibleState.bookIdx][2]));
        chapInp.value = v;
        bibleState.chapter = v;
        loadBibleChapter();
    });

    // Translation select
    const transSel = el('select', { class: 'bible-select', id: 'bible-trans-sel',
        onchange: () => { bibleState.translation = transSel.value; loadBibleChapter(); } });
    BIBLE_TRANSLATIONS.forEach(([name, code]) => transSel.appendChild(el('option', { value: code }, name)));
    transSel.value = bibleState.translation;

    const prevBtn = el('button', { class: 'sermon-btn', onclick: () => bibleNav(-1) }, '◀');
    const nextBtn = el('button', { class: 'sermon-btn', onclick: () => bibleNav(+1) }, '▶');

    const controls = el('div', { class: 'bible-controls' },
        bookSel, chapInp, transSel, prevBtn, nextBtn);

    // M'Cheyne readings
    const mcheyneDiv = el('div', { id: 'mcheyne-readings', class: 'mcheyne-readings' });
    const mcheyneLabel = el('span', { class: 'source-label', style: 'margin-right:6px' }, "Today's M'Cheyne:");
    renderMcheyne(mcheyneDiv);

    const textDiv = el('div', { id: 'bible-text' },
        el('span', { class: 'status-label' }, 'Loading…'));

    const scroll = el('div', { style: 'overflow-y:auto;flex:1' }, textDiv);

    const box = el('div', { class: 'tab-content', style: 'display:flex;flex-direction:column;height:100%' },
        controls,
        el('div', { class: 'flex-row', style: 'margin-bottom:8px;flex-wrap:wrap' }, mcheyneLabel, mcheyneDiv),
        scroll);

    panel.innerHTML = '';
    panel.appendChild(box);
    loadBibleChapter();
}

function applyBibleState() {
    const bookSel  = document.getElementById('bible-book-sel');
    const chapInp  = document.getElementById('bible-chap-inp');
    const transSel = document.getElementById('bible-trans-sel');
    if (!bookSel) return;
    bookSel.value  = bibleState.bookIdx;
    chapInp.max    = BIBLE_BOOKS[bibleState.bookIdx][2];
    chapInp.value  = bibleState.chapter;
    transSel.value = bibleState.translation;
}

function bibleNav(delta) {
    let bookIdx = bibleState.bookIdx;
    let chapter = bibleState.chapter + delta;
    const maxCh = BIBLE_BOOKS[bookIdx][2];
    if (chapter < 1) {
        bookIdx = Math.max(0, bookIdx - 1);
        chapter = BIBLE_BOOKS[bookIdx][2];
    } else if (chapter > maxCh) {
        bookIdx = Math.min(BIBLE_BOOKS.length - 1, bookIdx + 1);
        chapter = 1;
    }
    bibleState.bookIdx = bookIdx;
    bibleState.chapter = chapter;
    applyBibleState();
    loadBibleChapter();
}

async function loadBibleChapter() {
    const textDiv = document.getElementById('bible-text');
    if (!textDiv) return;
    textDiv.innerHTML = '<span class="status-label">Loading…</span>';

    const book = BIBLE_BOOKS[bibleState.bookIdx];
    const params = new URLSearchParams({
        book_id:     book[1],
        chapter:     bibleState.chapter,
        translation: bibleState.translation,
    });
    try {
        const data = await api('bible.php?' + params);
        renderBibleChapter(data);
    } catch(e) {
        textDiv.textContent = 'Could not load chapter: ' + e.message;
    }
}

function renderBibleChapter(data) {
    const textDiv = document.getElementById('bible-text');
    if (!textDiv) return;
    textDiv.innerHTML = '';

    if (data.error) { textDiv.textContent = data.error; return; }

    const verses = data.verses || [];
    if (!verses.length) { textDiv.textContent = 'No text available.'; return; }

    // Group into paragraphs of 5 verses
    for (let i = 0; i < verses.length; i += 5) {
        const p = el('p', { class: 'bible-paragraph' });
        for (let j = i; j < Math.min(i+5, verses.length); j++) {
            const v = verses[j];
            p.appendChild(el('sup', { class: 'verse-num' }, String(v.verse)));
            p.appendChild(document.createTextNode(v.text + ' '));
        }
        textDiv.appendChild(p);
    }

    if (data.citation) {
        textDiv.appendChild(el('span', { class: 'bible-citation' }, data.citation));
    }
}

function renderMcheyne(container) {
    // Calculate today's M'Cheyne readings client-side
    const readings = getMcheyneReadings(new Date());
    container.innerHTML = '';
    for (const [bookIdx, chapter] of readings) {
        const name = BIBLE_BOOKS[bookIdx][0];
        const btn = el('button', { class: 'mcheyne-btn',
            onclick: () => { bibleState.bookIdx = bookIdx; bibleState.chapter = chapter; applyBibleState(); loadBibleChapter(); }
        }, `${name} ${chapter}`);
        container.appendChild(btn);
    }
}

function getMcheyneReadings(date) {
    const STREAMS = [
        ['GEN','EXO','LEV','NUM','DEU','JOS','JDG','RUT','1SA','2SA','1KI','2KI','1CH','2CH','EZR','NEH','EST','JOB','PSA','PRO','ECC','SNG','ISA','JER','LAM','EZK','DAN','HOS','JOL','AMO','OBA','JON','MIC','NAH','HAB','ZEP','HAG','ZEC','MAL'],
        ['EZR','NEH','EST','JOB','PSA','PRO','ECC','SNG','ISA','JER','LAM','EZK','DAN','HOS','JOL','AMO','OBA','JON','MIC','NAH','HAB','ZEP','HAG','ZEC','MAL'],
        ['MAT','MRK','LUK','JHN','ACT','ROM','1CO','2CO','GAL','EPH','PHP','COL','1TH','2TH','1TI','2TI','TIT','PHM','HEB','JAS','1PE','2PE','1JN','2JN','3JN','JUD','REV'],
        ['ACT','ROM','1CO','2CO','GAL','EPH','PHP','COL','1TH','2TH','1TI','2TI','TIT','PHM','HEB','JAS','1PE','2PE','1JN','2JN','3JN','JUD','REV','MAT','MRK','LUK','JHN'],
    ];
    const bookIdMap = {};
    BIBLE_BOOKS.forEach(([,id,chapters], i) => { bookIdMap[id] = [i, chapters]; });

    const start = new Date(date.getFullYear(), 0, 1);
    const dayOfYear = Math.floor((date - start) / 86400000) + 1;

    return STREAMS.map(stream => {
        const total = stream.reduce((s, id) => s + bookIdMap[id][1], 0);
        let pos = (dayOfYear - 1) % total;
        for (const id of stream) {
            const [idx, chapters] = bookIdMap[id];
            if (pos < chapters) return [idx, pos + 1];
            pos -= chapters;
        }
        return [0, 1];
    });
}

/* ── PRAYER TAB ────────────────────────────────────────────────────── */
function initPrayer() {
    const panel = document.getElementById('tab-prayer');
    panel.innerHTML = `
    <div class="tab-content">
      <div class="prayer-toolbar">
        <button class="sermon-btn" id="prayer-reset-btn">Reset prayers</button>
      </div>
      <div class="prayer-add-row">
        <input type="text" class="prayer-input" id="prayer-new-input" placeholder="Add a prayer item…">
        <button class="sermon-btn" id="prayer-add-btn">Add</button>
      </div>
      <div class="prayer-list" id="prayer-list"></div>
    </div>`;

    document.getElementById('prayer-add-btn').onclick = addPrayer;
    document.getElementById('prayer-new-input').addEventListener('keydown', e => { if (e.key==='Enter') addPrayer(); });
    document.getElementById('prayer-reset-btn').onclick = resetPrayers;

    loadPrayer();
}

async function loadPrayer() {
    try {
        const data = await api('prayers.php');
        prayerData = data.prayers || [];
        renderPrayer();
    } catch(e) {
        document.getElementById('prayer-list').textContent = 'Could not load prayers.';
    }
}

function renderPrayer() {
    const list = document.getElementById('prayer-list');
    if (!list) return;
    list.innerHTML = '';

    const undone = prayerData.filter(p => !p.done);
    const done   = prayerData.filter(p => p.done);

    undone.forEach((item, i) => {
        list.appendChild(makePrayerItem(item, prayerData.indexOf(item), undone.length, i));
    });

    if (done.length) {
        list.appendChild(el('div', { class: 'done-divider' }, `Prayed (${done.length})`));
        done.forEach(item => list.appendChild(makePrayerItem(item, prayerData.indexOf(item), 0, 0)));
    }
}

function makePrayerItem(item, dataIdx, undoneTotal, undonePos) {
    const cb = el('input', { type: 'checkbox' });
    cb.checked = item.done;
    cb.onchange = () => { prayerData[dataIdx].done = cb.checked; savePrayer(); renderPrayer(); };

    const txt = el('span', { class: 'prayer-text' }, item.text);
    const row = el('div', { class: 'prayer-item' + (item.done ? ' done' : '') }, cb, txt);

    if (!item.done) {
        const upBtn = el('button', { class: 'prayer-move-btn', title: 'Move up' }, '▲');
        const dnBtn = el('button', { class: 'prayer-move-btn', title: 'Move down' }, '▼');
        upBtn.disabled = undonePos === 0;
        dnBtn.disabled = undonePos === undoneTotal - 1;
        upBtn.onclick = () => swapPrayer(dataIdx, -1);
        dnBtn.onclick = () => swapPrayer(dataIdx, +1);

        const addSubBtn = el('button', { class: 'prayer-move-btn', title: 'Add sub-point' }, '＋');
        addSubBtn.onclick = () => {
            addInputRow.classList.toggle('hidden');
            if (!addInputRow.classList.contains('hidden')) subInp.focus();
        };

        const delBtn = el('button', { class: 'prayer-move-btn', title: 'Delete prayer' }, '✕');
        delBtn.onclick = () => {
            prayerData.splice(dataIdx, 1);
            savePrayer();
            renderPrayer();
        };
        row.append(upBtn, dnBtn, addSubBtn, delBtn);
    }

    // Sub-items
    const children = item.children || [];
    const subList = el('div', { class: 'prayer-sublist' });
    children.forEach((child, ci) => subList.appendChild(makeSubPrayerItem(child, dataIdx, ci)));

    // Inline add-sub-point input
    const subInp = el('input', { type: 'text', class: 'prayer-sub-input', placeholder: 'Add sub-point…' });
    const confirmBtn = el('button', { class: 'sermon-btn' }, 'Add');
    const addInputRow = el('div', { class: 'prayer-sub-add-row hidden' }, subInp, confirmBtn);

    const doAdd = () => {
        const t = subInp.value.trim();
        if (!t) return;
        if (!prayerData[dataIdx].children) prayerData[dataIdx].children = [];
        prayerData[dataIdx].children.push({ text: t, done: false });
        subInp.value = '';
        addInputRow.classList.add('hidden');
        savePrayer();
        renderPrayer();
    };
    confirmBtn.onclick = doAdd;
    subInp.addEventListener('keydown', e => {
        if (e.key === 'Enter') doAdd();
        if (e.key === 'Escape') addInputRow.classList.add('hidden');
    });

    return el('div', { class: 'prayer-item-wrapper' }, row, subList, addInputRow);
}

function makeSubPrayerItem(child, parentIdx, childIdx) {
    const cb = el('input', { type: 'checkbox' });
    cb.checked = child.done;
    cb.onchange = () => {
        prayerData[parentIdx].children[childIdx].done = cb.checked;
        savePrayer();
        renderPrayer();
    };

    const txt = el('span', { class: 'prayer-text' }, child.text);

    const delBtn = el('button', { class: 'prayer-move-btn', title: 'Remove sub-point' }, '✕');
    delBtn.onclick = () => {
        prayerData[parentIdx].children.splice(childIdx, 1);
        savePrayer();
        renderPrayer();
    };

    return el('div', { class: 'prayer-subitem' + (child.done ? ' done' : '') }, cb, txt, delBtn);
}

function swapPrayer(idx, delta) {
    const target = idx + delta;
    if (target < 0 || target >= prayerData.length) return;
    [prayerData[idx], prayerData[target]] = [prayerData[target], prayerData[idx]];
    savePrayer();
    renderPrayer();
}

function addPrayer() {
    const inp = document.getElementById('prayer-new-input');
    const text = inp.value.trim();
    if (!text) return;
    prayerData.push({ text, done: false });
    inp.value = '';
    savePrayer();
    renderPrayer();
}

function resetPrayers() {
    prayerData = prayerData.map(p => ({ ...p, done: false }));
    savePrayer();
    renderPrayer();
}

async function savePrayer() {
    try {
        await api('prayers.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prayers: prayerData }),
        });
    } catch(e) {}
}

/* ── NOTES TAB ─────────────────────────────────────────────────────── */
function initNotes() {
    const panel = document.getElementById('tab-notes');
    panel.innerHTML = `
    <div class="tab-content" style="display:flex;flex-direction:column;height:100%">
      <div class="section-title" style="margin-bottom:8px">📝 Notes</div>
      <div class="notes-status" id="notes-status"></div>
      <textarea id="notes-area" placeholder="Your notes…"></textarea>
    </div>`;

    document.getElementById('notes-area').addEventListener('input', notesChanged);
    loadNotes();
}

async function loadNotes() {
    try {
        const data = await api('notes.php');
        const ta = document.getElementById('notes-area');
        if (ta) ta.value = data.text || '';
    } catch(e) {}
}

function notesChanged() {
    const status = document.getElementById('notes-status');
    if (status) status.textContent = 'Unsaved…';
    clearTimeout(notesTimer);
    notesTimer = setTimeout(saveNotes, 1500);
}

async function saveNotes() {
    const ta = document.getElementById('notes-area');
    const status = document.getElementById('notes-status');
    if (!ta) return;
    try {
        await api('notes.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: ta.value }),
        });
        if (status) status.textContent = 'Saved';
        setTimeout(() => { if (status) status.textContent = ''; }, 2000);
    } catch(e) {
        if (status) status.textContent = 'Save failed';
    }
}

/* ── SERMONS TAB ───────────────────────────────────────────────────── */
function initSermons() {
    const panel = document.getElementById('tab-sermons');
    panel.innerHTML = `
    <div class="sermons-paned">
      <div class="sermons-left">
        <span class="source-label">MY SERMONS</span>
        <button class="sermon-btn" id="sermon-new-btn" style="margin:6px 0 0 0">＋ New</button>
        <div class="sermons-list-scroll" id="sermon-list"></div>
      </div>
      <div class="sermons-right">
        <div class="sermon-toolbar">
          <input type="text" class="sermon-title-entry" id="sermon-title" placeholder="Sermon title…">
          <button class="sermon-btn" id="sermon-save-btn">💾 Save</button>
          <button class="sermon-btn" id="sermon-delete-btn">🗑 Delete</button>
        </div>
        <div class="sync-status" id="sermon-status"></div>
        <textarea class="sermon-text-area" id="sermon-body" placeholder="Start writing your sermon…"></textarea>
      </div>
    </div>`;

    document.getElementById('sermon-new-btn').onclick    = newSermon;
    document.getElementById('sermon-save-btn').onclick   = saveSermon;
    document.getElementById('sermon-delete-btn').onclick = deleteSermon;

    loadSermonList();
}

async function loadSermonList() {
    try {
        const data = await api('sermons.php');
        renderSermonList(data.sermons || []);
    } catch(e) {}
}

function renderSermonList(sermons) {
    const list = document.getElementById('sermon-list');
    if (!list) return;
    list.innerHTML = '';
    sermons.forEach(name => {
        const btn = el('button', { class: 'sermon-list-item' + (name === currentSermonFile ? ' selected' : ''),
            onclick: () => loadSermon(name) }, name.replace(/\.txt$/, ''));
        list.appendChild(btn);
    });
}

function newSermon() {
    currentSermonFile = null;
    document.getElementById('sermon-title').value = '';
    document.getElementById('sermon-body').value  = '';
    document.getElementById('sermon-status').textContent = '';
    document.getElementById('sermon-title').focus();
    document.querySelectorAll('.sermon-list-item').forEach(b => b.classList.remove('selected'));
}

async function loadSermon(fname) {
    try {
        const data = await api('sermons.php?file=' + encodeURIComponent(fname));
        document.getElementById('sermon-title').value = fname.replace(/\.txt$/, '');
        document.getElementById('sermon-body').value  = data.text || '';
        document.getElementById('sermon-status').textContent = '';
        currentSermonFile = fname;
        document.querySelectorAll('.sermon-list-item').forEach(b => {
            b.classList.toggle('selected', b.textContent === fname.replace(/\.txt$/,''));
        });
    } catch(e) {
        document.getElementById('sermon-status').textContent = 'Load failed: ' + e.message;
    }
}

async function saveSermon() {
    const title  = document.getElementById('sermon-title').value.trim();
    const body   = document.getElementById('sermon-body').value;
    const status = document.getElementById('sermon-status');
    if (!title) { document.getElementById('sermon-title').placeholder = 'Please enter a title!'; return; }

    try {
        const data = await api('sermons.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, text: body, old_file: currentSermonFile }),
        });
        currentSermonFile = data.file;
        status.textContent = '✅ Saved';
        setTimeout(() => { status.textContent = ''; }, 2000);
        loadSermonList();
    } catch(e) {
        status.textContent = '❌ Save failed: ' + e.message;
    }
}

async function deleteSermon() {
    if (!currentSermonFile) return;
    if (!confirm(`Delete "${currentSermonFile.replace(/\.txt$/,'')}"?`)) return;
    try {
        await api('sermons.php?file=' + encodeURIComponent(currentSermonFile), { method: 'DELETE' });
        newSermon();
        loadSermonList();
    } catch(e) {
        document.getElementById('sermon-status').textContent = '❌ Delete failed: ' + e.message;
    }
}

/* ── SETTINGS ──────────────────────────────────────────────────────── */
let settingsState = {};

function openSettings() {
    settingsState = {
        theme:            prefs.theme,
        font_size:        prefs.font_size,
        weather_location: prefs.weather_location,
        weather_lat:      prefs.weather_lat,
        weather_lon:      prefs.weather_lon,
        api_bible_key:    prefs.api_bible_key,
        tab_order:        [...prefs.tab_order],
        visible_tabs:     [...prefs.visible_tabs],
        selected_loc:     null,
    };
    renderSettingsBody();
    document.getElementById('settings-modal').hidden = false;
}

function closeSettings() {
    document.getElementById('settings-modal').hidden = true;
}

function renderSettingsBody() {
    const body = document.getElementById('settings-body');
    body.innerHTML = '';

    // Theme
    body.appendChild(el('div', { class: 'settings-section-label' }, 'APPEARANCE'));
    const themeRow = el('div', { class: 'settings-row' });
    themeRow.appendChild(el('label', {}, 'Theme:'));
    ['dark','light'].forEach(t => {
        const rb = el('input', { type: 'radio', name: 'theme', value: t });
        rb.checked = settingsState.theme === t;
        rb.onchange = () => { settingsState.theme = t; };
        themeRow.appendChild(rb);
        themeRow.appendChild(el('label', {}, t.charAt(0).toUpperCase() + t.slice(1)));
    });
    body.appendChild(themeRow);

    const fontRow = el('div', { class: 'settings-row' });
    fontRow.appendChild(el('label', {}, 'Font size:'));
    const decBtn = el('button', { class: 'sermon-btn', onclick: () => { if (settingsState.font_size > 9) { settingsState.font_size--; fontLbl.textContent = settingsState.font_size; } } }, '−');
    const fontLbl = el('span', { style: 'min-width:24px;text-align:center' }, String(settingsState.font_size));
    const incBtn = el('button', { class: 'sermon-btn', onclick: () => { if (settingsState.font_size < 24) { settingsState.font_size++; fontLbl.textContent = settingsState.font_size; } } }, '+');
    fontRow.append(decBtn, fontLbl, incBtn);
    body.appendChild(fontRow);

    // Weather
    body.appendChild(el('div', { class: 'settings-section-label' }, 'WEATHER LOCATION'));
    const currentLocLbl = el('div', { class: 'status-label', style:'padding:0;margin-bottom:4px' },
        'Current: ' + (prefs.weather_location || 'Auto-detect'));
    body.appendChild(currentLocLbl);

    const searchRow = el('div', { class: 'flex-row' });
    const locInp = el('input', { type: 'text', class: 'settings-input flex-1', placeholder: 'Search for a town or city…', value: settingsState.weather_location });
    const searchBtn = el('button', { class: 'sermon-btn', onclick: () => searchLocation(locInp.value, resultsDiv, currentLocLbl) }, 'Search');
    locInp.addEventListener('keydown', e => { if (e.key==='Enter') searchBtn.click(); });
    searchRow.append(locInp, searchBtn);
    body.appendChild(searchRow);

    const resultsDiv = el('div', { class: 'loc-results' });
    body.appendChild(resultsDiv);

    const autoBtn = el('button', { class: 'sermon-btn', onclick: () => {
        settingsState.weather_location = '';
        settingsState.weather_lat = null;
        settingsState.weather_lon = null;
        currentLocLbl.textContent = 'Current: Auto-detect';
        resultsDiv.innerHTML = '';
    } }, 'Use auto-detect (IP location)');
    body.appendChild(autoBtn);

    // API.Bible key
    body.appendChild(el('div', { class: 'settings-section-label' }, 'BIBLE (API.BIBLE)'));
    const keyRow = el('div', { class: 'settings-row' });
    keyRow.appendChild(el('label', {}, 'API key:'));
    const keyPlaceholder = prefs.api_bible_key_set ? 'Key saved — paste a new one to replace it' : 'Paste your API.Bible key here…';
    const keyInp = el('input', { type: 'password', class: 'settings-input flex-1', placeholder: keyPlaceholder });
    keyInp.oninput = () => { settingsState.api_bible_key = keyInp.value; };
    const showCb = el('input', { type: 'checkbox' });
    showCb.onchange = () => { keyInp.type = showCb.checked ? 'text' : 'password'; };
    keyRow.append(keyInp, showCb, el('label', {}, 'Show'));
    if (prefs.api_bible_key_set) {
        keyRow.appendChild(el('span', { style: 'color:#66bb6a;font-size:12px' }, '✓ Set'));
    }
    body.appendChild(keyRow);

    // Tabs order & visibility
    body.appendChild(el('div', { class: 'settings-section-label' }, 'TABS — ORDER & VISIBILITY'));
    const tabsBox = el('div', { id: 'settings-tabs-box' });
    body.appendChild(tabsBox);
    renderSettingsTabs(tabsBox);
    body.appendChild(el('div', { class: 'status-label', style: 'padding:0' }, '(At least one tab must remain visible)'));

    // Change password (all users)
    body.appendChild(el('div', { class: 'settings-section-label' }, 'CHANGE PASSWORD'));
    const pwRow1 = el('div', { class: 'settings-row' });
    pwRow1.appendChild(el('label', {}, 'New password:'));
    const pwInp = el('input', { type: 'password', class: 'settings-input flex-1', placeholder: 'At least 8 characters' });
    pwRow1.appendChild(pwInp);
    body.appendChild(pwRow1);

    const pwRow2 = el('div', { class: 'settings-row' });
    pwRow2.appendChild(el('label', {}, 'Confirm:'));
    const pwInp2 = el('input', { type: 'password', class: 'settings-input flex-1', placeholder: 'Repeat new password' });
    pwRow2.appendChild(pwInp2);
    body.appendChild(pwRow2);

    const pwStatus = el('div', { style: 'font-size:12px;min-height:18px' });
    const pwBtn = el('button', { class: 'sermon-btn', style: 'margin-left:0', onclick: async () => {
        const p1 = pwInp.value, p2 = pwInp2.value;
        if (!p1) return;
        if (p1 !== p2) { pwStatus.style.color='#ef5350'; pwStatus.textContent='Passwords do not match.'; return; }
        if (p1.length < 8) { pwStatus.style.color='#ef5350'; pwStatus.textContent='Must be at least 8 characters.'; return; }
        try {
            const res = await api('access.php', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'change_password', new_password: p1 }),
            });
            if (res.error) { pwStatus.style.color='#ef5350'; pwStatus.textContent='❌ ' + res.error; }
            else { pwStatus.style.color='#66bb6a'; pwStatus.textContent='✅ Password changed.'; pwInp.value=''; pwInp2.value=''; }
        } catch(e) { pwStatus.style.color='#ef5350'; pwStatus.textContent='❌ ' + e.message; }
    } }, 'Update password');
    body.appendChild(el('div', { class: 'settings-row' }, pwBtn, pwStatus));

    // Admin: user list + access requests
    if (window.IS_ADMIN) {
        body.appendChild(el('div', { class: 'settings-section-label' }, 'USERS'));
        const usersBox = el('div', { id: 'users-box' },
            el('span', { class: 'status-label', style: 'padding:0' }, 'Loading…'));
        body.appendChild(usersBox);
        loadUserList(usersBox);

        body.appendChild(el('div', { class: 'settings-section-label' }, 'ACCESS REQUESTS'));
        const reqBox = el('div', { id: 'access-requests-box' },
            el('span', { class: 'status-label', style: 'padding:0' }, 'Loading…'));
        body.appendChild(reqBox);
        loadAccessRequests(reqBox);
    }
}

function renderSettingsTabs(container) {
    container.innerHTML = '';
    const TAB_LABELS = {
        spurgeon:'📖 Devotional', news:'📰 News', weather:'🌤️ Weather',
        sermons:'✍️ Sermons', bible:'📜 Bible', prayer:'🙏 Prayer', notes:'📝 Notes',
    };
    const n = settingsState.tab_order.length;
    settingsState.tab_order.forEach((key, i) => {
        const row = el('div', { class: 'settings-tab-row' });

        const upBtn = el('button', { class: 'sermon-btn', style: 'min-width:28px;padding:2px 6px',
            onclick: () => { if (i > 0) { [settingsState.tab_order[i], settingsState.tab_order[i-1]] = [settingsState.tab_order[i-1], settingsState.tab_order[i]]; renderSettingsTabs(container); } }
        }, '↑');
        upBtn.disabled = i === 0;

        const dnBtn = el('button', { class: 'sermon-btn', style: 'min-width:28px;padding:2px 6px',
            onclick: () => { if (i < n-1) { [settingsState.tab_order[i], settingsState.tab_order[i+1]] = [settingsState.tab_order[i+1], settingsState.tab_order[i]]; renderSettingsTabs(container); } }
        }, '↓');
        dnBtn.disabled = i === n - 1;

        const cb = el('input', { type: 'checkbox' });
        cb.checked = settingsState.visible_tabs.includes(key);
        cb.onchange = () => {
            if (cb.checked) {
                settingsState.visible_tabs.push(key);
            } else {
                settingsState.visible_tabs = settingsState.visible_tabs.filter(k => k !== key);
            }
        };

        row.append(upBtn, dnBtn, cb, el('label', {}, TAB_LABELS[key] || key));
        container.appendChild(row);
    });
}

async function searchLocation(query, resultsDiv, currentLocLbl) {
    if (!query.trim()) return;
    resultsDiv.innerHTML = '<span class="status-label" style="padding:4px">Searching…</span>';
    try {
        const data = await api('weather.php?geocode=' + encodeURIComponent(query));
        resultsDiv.innerHTML = '';
        if (!data.results || !data.results.length) {
            resultsDiv.textContent = 'No results found.';
            return;
        }
        data.results.forEach(r => {
            const lbl = [r.name, r.admin1, r.country].filter(Boolean).join(', ');
            const btn = el('button', { class: 'loc-result-btn',
                onclick: () => {
                    settingsState.weather_location = r.name;
                    settingsState.weather_lat      = r.latitude;
                    settingsState.weather_lon      = r.longitude;
                    settingsState.selected_loc     = lbl;
                    currentLocLbl.textContent = 'Current: ' + lbl;
                    resultsDiv.innerHTML = '';
                }
            }, lbl);
            resultsDiv.appendChild(btn);
        });
    } catch(e) {
        resultsDiv.textContent = 'Search failed: ' + e.message;
    }
}

async function saveSettings() {
    if (!settingsState.visible_tabs.length) {
        alert('At least one tab must remain visible.');
        return;
    }
    prefs.theme            = settingsState.theme;
    prefs.font_size        = settingsState.font_size;
    prefs.weather_location = settingsState.weather_location;
    prefs.weather_lat      = settingsState.weather_lat;
    prefs.weather_lon      = settingsState.weather_lon;
    prefs.api_bible_key    = settingsState.api_bible_key || '';
    prefs.tab_order        = settingsState.tab_order;
    prefs.visible_tabs     = settingsState.visible_tabs;

    try {
        await api('prefs.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(prefs),
        });
    } catch(e) {}

    applyTheme();
    buildSidebar();
    // Ensure active tab is still visible
    if (!prefs.visible_tabs.includes(activeTab)) {
        const first = prefs.tab_order.find(k => prefs.visible_tabs.includes(k));
        if (first) switchTab(first);
    }
    // Reload weather if location changed
    if (tabLoaded['weather']) {
        tabLoaded['weather'] = false;
        if (activeTab === 'weather') { tabLoaded['weather'] = true; initWeather(); }
    }

    closeSettings();
}

/* ── USER LIST (admin only) ────────────────────────────────────────── */
async function loadUserList(container) {
    try {
        const data = await api('access.php?action=list_users');
        container.innerHTML = '';
        const users = data.users || [];
        if (!users.length) {
            container.appendChild(el('div', { class: 'status-label', style: 'padding:0' }, 'No users found.'));
            return;
        }
        users.forEach(username => {
            const isAdmin = username === 'paul';
            const row = el('div', { style: 'display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--header-border)' });
            const nameLbl = el('span', { style: 'flex:1;font-size:14px' }, username);
            if (isAdmin) nameLbl.appendChild(el('span', { style: 'font-size:11px;color:var(--accent);margin-left:6px' }, '(admin)'));
            row.appendChild(nameLbl);

            if (!isAdmin) {
                const delBtn = el('button', { class: 'cancel-btn', style: 'font-size:12px;padding:3px 10px',
                    onclick: async () => {
                        if (!confirm(`Delete user "${username}" and all their data?`)) return;
                        try {
                            await api('access.php', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ action: 'delete_user', username }),
                            });
                            row.remove();
                        } catch(e) { alert('Delete failed: ' + e.message); }
                    }
                }, 'Delete');
                row.appendChild(delBtn);
            }
            container.appendChild(row);
        });
    } catch(e) {
        container.textContent = 'Could not load users.';
    }
}

/* ── ACCESS REQUESTS (admin only) ──────────────────────────────────── */
async function loadAccessRequests(container) {
    try {
        const data = await api('access.php?action=list');
        const pending = (data.requests || []).filter(r => r.status === 'pending');
        container.innerHTML = '';

        if (!pending.length) {
            container.appendChild(el('div', { class: 'status-label', style: 'padding:0' }, 'No pending requests.'));
            return;
        }

        pending.forEach(r => {
            const row = el('div', { style: 'background:var(--card-bg);border-radius:8px;padding:10px 12px;margin-bottom:6px' });

            const info = el('div', { style: 'margin-bottom:6px' },
                el('strong', {}, r.username),
                el('span',   { style: 'color:var(--subtext);font-size:12px;margin-left:8px' }, r.name),
            );
            if (r.reason) {
                info.appendChild(el('div', { style: 'font-size:12px;color:var(--subtext);margin-top:2px' }, r.reason));
            }
            info.appendChild(el('div', { style: 'font-size:11px;color:var(--status-col);margin-top:2px' }, r.requested));

            const approveBtn = el('button', { class: 'save-btn', style: 'padding:4px 14px;font-size:12px' }, 'Approve');
            const denyBtn    = el('button', { class: 'cancel-btn', style: 'font-size:12px;margin-left:6px' }, 'Deny');
            const resultDiv  = el('div', { style: 'margin-top:6px;font-size:12px' });

            approveBtn.onclick = async () => {
                approveBtn.disabled = true; denyBtn.disabled = true;
                try {
                    const res = await api('access.php', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ action: 'approve', username: r.username }),
                    });
                    if (res.error) {
                        resultDiv.style.color = '#ef5350';
                        resultDiv.textContent = '❌ ' + res.error;
                    } else {
                        resultDiv.style.color = '#66bb6a';
                        if (res.user_set_password) {
                            resultDiv.innerHTML = `✅ Approved! <strong>${res.username}</strong> can now log in with the password they chose.`;
                        } else {
                            resultDiv.innerHTML = `✅ Approved! Username: <strong>${res.username}</strong> &nbsp; Password: <strong>${res.password}</strong> &nbsp; <em>(share this once — it won't show again)</em>`;
                        }
                    }
                } catch(e) {
                    resultDiv.style.color = '#ef5350';
                    resultDiv.textContent = '❌ ' + e.message;
                }
            };

            denyBtn.onclick = async () => {
                if (!confirm(`Deny request from ${r.username}?`)) return;
                await api('access.php', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'deny', username: r.username }),
                });
                row.remove();
            };

            const btns = el('div', {}, approveBtn, denyBtn);
            row.append(info, btns, resultDiv);
            container.appendChild(row);
        });
    } catch(e) {
        container.textContent = 'Could not load requests.';
    }
}

async function savePrefsSilent() {
    try {
        await api('prefs.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(prefs),
        });
    } catch(e) {}
}
