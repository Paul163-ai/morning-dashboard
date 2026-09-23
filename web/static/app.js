/* ── Morning Dashboard — app.js ──────────────────────────────────── */

const ALL_TABS = ['daily','spurgeon','systematics','news','weather','bible','prayer','notes','sermons','resources'];

const TAB_META = {
    daily:        { emoji: '🌅', label: 'Daily Bible', accent: '#26a69a' },
    spurgeon:     { emoji: '📖', label: 'Devotional',  accent: '#f0a500' },
    systematics:  { emoji: '📚', label: 'Theology',    accent: '#7e57c2' },
    news:         { emoji: '📰', label: 'News',        accent: '#4a9eff' },
    weather:      { emoji: '🌤️', label: 'Weather',     accent: '#00bcd4' },
    sermons:      { emoji: '✍️', label: 'Sermons',     accent: '#66bb6a' },
    bible:        { emoji: '📜', label: 'Bible',       accent: '#ffd54f' },
    prayer:       { emoji: '🙏', label: 'Prayer',      accent: '#ef5350' },
    notes:        { emoji: '📝', label: 'Notes',       accent: '#ff7043' },
    resources:    { emoji: '🔗', label: 'Resources',   accent: '#8d6e63' },
};

const RESOURCE_LINKS = [
    { title: 'John Owen', desc: 'Writings and resources on John Owen', url: 'https://paullintott.uk/john-owen' },
    { title: 'John Calvin', desc: 'Writings and resources on John Calvin', url: 'https://paullintott.uk/john-calvin' },
];

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
const IS_GUEST = window.IS_GUEST === true;
let prefs = window.INIT_PREFS;
let activeTab = null;
const tabLoaded = {};

// Spurgeon state
let spurgeonDate = new Date();
spurgeonDate.setHours(0,0,0,0);
let spurgeonNotesTimer = null;
let spurgeonNotesLoading = false;
let spurgeonOriginalReadings = [];
let spurgeonModernReadings = null;
let spurgeonVersion = (window.INIT_PREFS && window.INIT_PREFS.spurgeon_version === 'modern') ? 'modern' : 'original';
let spurgeonOriginalLoaded = false;
let spurgeonModernLoaded = false;

// Bible state
let bibleState = { bookIdx: 0, chapter: 1, translation: 'web' };

// Prayer state
let prayerData = [];

// Notes state
let notesTimer = null;

// Sermons state
let currentSermonFile = null;

// Systematics state
let systematicsDate = new Date();
systematicsDate.setHours(0,0,0,0);

// Daily Bible state
let dailyDate = new Date();
dailyDate.setHours(0,0,0,0);
const dailyChapterCache = {}; // "translation|bookId|chapter" -> bible.php response

/* ── Helpers ───────────────────────────────────────────────────────── */
function dateToISO(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth()+1).padStart(2,'0');
    const day = String(d.getDate()).padStart(2,'0');
    return `${y}-${m}-${day}`;
}

// 1-based day of year, computed in UTC so a DST change doesn't shave an hour
// off the difference and land on the previous day.
function dayOfYearOf(d) {
    const start = Date.UTC(d.getFullYear(), 0, 1);
    const today = Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
    return Math.round((today - start) / 86400000) + 1;
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

    if (!IS_GUEST) {
        // Settings button
        document.getElementById('settings-btn').addEventListener('click', openSettings);
        document.getElementById('close-settings-btn').addEventListener('click', closeSettings);
        document.getElementById('cancel-settings-btn').addEventListener('click', closeSettings);
        document.getElementById('save-settings-btn').addEventListener('click', saveSettings);
        document.getElementById('settings-modal').addEventListener('click', e => {
            if (e.target === e.currentTarget) closeSettings();
        });

        // Logout button
        document.getElementById('logout-btn').addEventListener('click', () => {
            api('logout.php', {method: 'POST'}).then(() => { location.href = '/login.php'; });
        });
    }

    // Collapse button
    document.getElementById('collapse-btn').addEventListener('click', toggleSidebar);

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
        case 'daily':    initDaily();    break;
        case 'spurgeon': initSpurgeon(); break;
        case 'news':     initNews();     break;
        case 'weather':  initWeather();  break;
        case 'bible':    initBible();    break;
        case 'prayer':   initPrayer();   break;
        case 'notes':    initNotes();    break;
        case 'sermons':  initSermons();  break;
        case 'systematics': initSystematics(); break;
        case 'resources': initResources(); break;
    }
}

/* ── RESOURCES TAB ─────────────────────────────────────────────────── */
function initResources() {
    const panel = document.getElementById('tab-resources');
    panel.innerHTML = `
    <div class="resources-pane">
      <div class="section-title">More Resources</div>
      <div class="resources-list">
        ${RESOURCE_LINKS.map(r => `
          <a class="resource-card" href="${escapeHtml(r.url)}" target="_blank" rel="noopener noreferrer">
            <div class="resource-card-title">${escapeHtml(r.title)}</div>
            <div class="resource-card-desc">${escapeHtml(r.desc)}</div>
          </a>`).join('')}
      </div>
    </div>`;
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
        <div class="section-title">Spurgeon's Morning and Evening</div>
        <div class="sermon-toolbar">
          <button class="sermon-btn" id="spur-prev">◀ Prev</button>
          <span class="section-title flex-1" style="text-align:center" id="spur-date-lbl"></span>
          <button class="sermon-btn" id="spur-next">Next ▶</button>
          <button class="sermon-btn" id="spur-today">Today</button>
        </div>
        <div class="sermon-toolbar" id="spur-version-toolbar" style="display:none">
          <button class="sermon-btn active" id="spur-version-original">Original</button>
          <button class="sermon-btn" id="spur-version-modern">✨ Modern</button>
          ${window.IS_ADMIN ? '<button class="sermon-btn" id="spur-modern-edit" style="display:none">✏️ Edit</button>' : ''}
        </div>
        <div class="spurgeon-reading-scroll">
          <div id="spurgeon-reading"><span class="status-label">Loading today's reading…</span></div>
        </div>
      </div>
      ${IS_GUEST ? '' : `
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
      </div>`}
    </div>`;

    document.getElementById('spur-prev').onclick  = () => spurgeonNav(-1);
    document.getElementById('spur-next').onclick  = () => spurgeonNav(+1);
    document.getElementById('spur-today').onclick = () => { spurgeonDate = new Date(); spurgeonDate.setHours(0,0,0,0); spurgeonRefresh(); };
    document.getElementById('spur-version-original').onclick = () => setSpurgeonVersion('original');
    document.getElementById('spur-version-modern').onclick   = () => setSpurgeonVersion('modern');
    if (window.IS_ADMIN) {
        document.getElementById('spur-modern-edit').onclick = enterSpurgeonEditMode;
    }

    if (!IS_GUEST) {
        document.getElementById('spurgeon-notes').addEventListener('input', spurgeonNotesChanged);
        document.getElementById('spur-export-btn').onclick = exportSpurgeonNotes;
        document.getElementById('spur-comment-submit').onclick = postSpurgeonComment;
        document.getElementById('spur-comment-input').addEventListener('keydown', e => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) postSpurgeonComment();
        });
    }

    spurgeonRefresh();
}

function spurgeonNav(delta) {
    spurgeonDate = new Date(spurgeonDate.getTime() + delta * 86400000);
    spurgeonRefresh();
}

function spurgeonRefresh() {
    const dateStr = formatDateFull(spurgeonDate);
    document.getElementById('spur-date-lbl').textContent = dateStr;
    if (!IS_GUEST) document.getElementById('spur-notes-date-lbl').textContent = 'Notes — ' + dateStr;
    document.getElementById('spurgeon-reading').innerHTML = '<span class="status-label">Loading…</span>';
    spurgeonModernReadings = null;
    spurgeonOriginalLoaded = false;
    spurgeonModernLoaded = false;
    document.getElementById('spur-version-toolbar').style.display = 'none';
    document.getElementById('spur-version-original').classList.toggle('active', spurgeonVersion === 'original');
    document.getElementById('spur-version-modern').classList.toggle('active', spurgeonVersion === 'modern');
    if (window.IS_ADMIN) {
        document.getElementById('spur-modern-edit').style.display = 'none';
        document.getElementById('spur-modern-edit').textContent = '✏️ Edit';
    }
    document.getElementById('spur-version-modern').disabled = false;
    loadSpurgeonReading();
    loadSpurgeonModern();
    if (!IS_GUEST) {
        loadSpurgeonNotes();
        loadSpurgeonComments();
    }
}

async function loadSpurgeonReading() {
    try {
        const data = await api('spurgeon.php?date=' + dateToISO(spurgeonDate));
        spurgeonOriginalReadings = data.readings || [];
        spurgeonOriginalLoaded = true;
        spurgeonRenderCurrent();
    } catch(e) {
        document.getElementById('spurgeon-reading').textContent = 'Could not load reading: ' + e.message;
    }
}

async function loadSpurgeonModern() {
    try {
        const data = await api('spurgeon_modern.php?date=' + dateToISO(spurgeonDate));
        if (data.am || data.pm) {
            spurgeonModernReadings = [
                { label: '☀️ Morning', text: data.am || '' },
                { label: '🌙 Evening', text: data.pm || '' },
            ];
            document.getElementById('spur-version-toolbar').style.display = '';
            document.getElementById('spur-version-modern').disabled = false;
            if (window.IS_ADMIN) document.getElementById('spur-modern-edit').textContent = '✏️ Edit';
        } else {
            spurgeonModernReadings = null;
            // Admins still see the toolbar so they can create a modern version
            document.getElementById('spur-version-toolbar').style.display = window.IS_ADMIN ? '' : 'none';
            if (window.IS_ADMIN) {
                document.getElementById('spur-version-modern').disabled = true;
                document.getElementById('spur-modern-edit').style.display = '';
                document.getElementById('spur-modern-edit').textContent = '✏️ Add Modern';
            }
        }
    } catch(e) {
        spurgeonModernReadings = null;
        document.getElementById('spur-version-toolbar').style.display = window.IS_ADMIN ? '' : 'none';
        if (window.IS_ADMIN) {
            document.getElementById('spur-version-modern').disabled = true;
            document.getElementById('spur-modern-edit').style.display = '';
            document.getElementById('spur-modern-edit').textContent = '✏️ Add Modern';
        }
    }
    spurgeonModernLoaded = true;
    spurgeonRenderCurrent();
}

// Renders whichever version is current once its data has arrived. The
// original and modern readings load concurrently, so this is the single
// place that decides what to paint once either fetch settles — it avoids a
// race where the fetch that lands second silently overwrites the display.
// If the preferred version is "modern" but no modern reading exists for
// this date, it falls back to original for this date only; the preference
// itself (spurgeonVersion) is left untouched so the next date with a modern
// reading still opens in modern.
function spurgeonRenderCurrent() {
    if (spurgeonVersion === 'modern') {
        if (spurgeonModernReadings) {
            renderSpurgeonReading(spurgeonModernReadings);
        } else if (spurgeonModernLoaded) {
            document.getElementById('spur-version-original').classList.add('active');
            document.getElementById('spur-version-modern').classList.remove('active');
            if (spurgeonOriginalLoaded) renderSpurgeonReading(spurgeonOriginalReadings);
        }
    } else if (spurgeonOriginalLoaded) {
        renderSpurgeonReading(spurgeonOriginalReadings);
    }
}

function setSpurgeonVersion(version) {
    if (version === spurgeonVersion) return;
    if (version === 'modern' && !spurgeonModernReadings) return;
    spurgeonVersion = version;
    document.getElementById('spur-version-original').classList.toggle('active', version === 'original');
    document.getElementById('spur-version-modern').classList.toggle('active', version === 'modern');
    if (window.IS_ADMIN) {
        document.getElementById('spur-modern-edit').style.display = version === 'modern' ? '' : 'none';
    }
    renderSpurgeonReading(version === 'modern' ? spurgeonModernReadings : spurgeonOriginalReadings);
    if (!IS_GUEST) {
        prefs.spurgeon_version = version;
        savePrefsSilent();
    }
}

function enterSpurgeonEditMode() {
    const am = spurgeonModernReadings?.[0]?.text ?? '';
    const pm = spurgeonModernReadings?.[1]?.text ?? '';
    const container = document.getElementById('spurgeon-reading');
    container.innerHTML = '';

    const makeLabel = (text) => {
        const s = document.createElement('span');
        s.className = 'section-heading';
        s.textContent = text;
        return s;
    };
    const amLabel  = makeLabel('☀️ Morning');
    const amArea   = document.createElement('textarea');
    amArea.id      = 'spur-edit-am';
    amArea.className = 'spur-edit-area';
    amArea.value   = am;
    amArea.rows    = 12;

    const hr = document.createElement('hr');
    hr.className = 'divider';

    const pmLabel  = makeLabel('🌙 Evening');
    const pmArea   = document.createElement('textarea');
    pmArea.id      = 'spur-edit-pm';
    pmArea.className = 'spur-edit-area';
    pmArea.value   = pm;
    pmArea.rows    = 12;

    const toolbar  = document.createElement('div');
    toolbar.className = 'sermon-toolbar';
    const saveBtn  = document.createElement('button');
    saveBtn.className = 'sermon-btn';
    saveBtn.textContent = 'Save';
    saveBtn.onclick = saveSpurgeonModern;
    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'sermon-btn';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.onclick = () => renderSpurgeonReading(spurgeonModernReadings ?? spurgeonOriginalReadings);
    toolbar.appendChild(saveBtn);
    toolbar.appendChild(cancelBtn);

    container.appendChild(amLabel);
    container.appendChild(amArea);
    container.appendChild(hr);
    container.appendChild(pmLabel);
    container.appendChild(pmArea);
    container.appendChild(toolbar);
    amArea.focus();
}

async function saveSpurgeonModern() {
    const amArea = document.getElementById('spur-edit-am');
    const pmArea = document.getElementById('spur-edit-pm');
    if (!amArea || !pmArea) return;
    const am = amArea.value;
    const pm = pmArea.value;
    try {
        await api('spurgeon_modern.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date: dateToISO(spurgeonDate), am, pm }),
        });
        spurgeonModernReadings = [
            { label: '☀️ Morning', text: am },
            { label: '🌙 Evening', text: pm },
        ];
        document.getElementById('spur-version-modern').disabled = false;
        document.getElementById('spur-modern-edit').textContent = '✏️ Edit';
        spurgeonVersion = 'modern';
        document.getElementById('spur-version-original').classList.remove('active');
        document.getElementById('spur-version-modern').classList.add('active');
        document.getElementById('spur-modern-edit').style.display = '';
        renderSpurgeonReading(spurgeonModernReadings);
        if (!IS_GUEST) {
            prefs.spurgeon_version = 'modern';
            savePrefsSilent();
        }
    } catch(e) {
        alert('Save failed: ' + e.message);
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

// Safe in element content and in quoted attribute values.
function escapeHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
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

// The seven divisions of the year (plus the Day 365 capstone), from
// Systematics/365-outline.md — each entry is the day-of-year its division
// begins on. Kept as a small static list rather than parsed at runtime,
// same pattern as the day files themselves.
const SYSTEMATICS_DIVISIONS = [
    { day: 1,   label: 'The Doctrine of the Word of God' },
    { day: 29,  label: 'The Doctrine of God' },
    { day: 99,  label: 'The Doctrine of Man' },
    { day: 127, label: 'The Doctrines of Christ and the Holy Spirit' },
    { day: 183, label: 'The Application of Redemption' },
    { day: 246, label: 'The Doctrine of the Church' },
    { day: 316, label: 'The Doctrine of the Future' },
    { day: 365, label: 'Capstone' },
];

/* ── SYSTEMATICS TAB ───────────────────────────────────────────────── */
function initSystematics() {
    const panel = document.getElementById('tab-systematics');
    panel.innerHTML = `
    <div class="systematics-pane">
      <div class="section-title">A Year in Systematic Theology</div>
      <div class="sermon-toolbar">
        <button class="sermon-btn" id="sys-prev">◀ Prev</button>
        <span class="section-title flex-1" style="text-align:center" id="sys-date-lbl"></span>
        <button class="sermon-btn" id="sys-next">Next ▶</button>
        <button class="sermon-btn" id="sys-today">Today</button>
      </div>
      <div class="sermon-toolbar">
        <select class="bible-select flex-1" id="sys-jump-select">
          <option value="" disabled selected>Jump to a section…</option>
          ${SYSTEMATICS_DIVISIONS.map(d => `<option value="${d.day}">${escapeHtml(d.label)}</option>`).join('')}
        </select>
      </div>
      <div class="systematics-reading-scroll">
        <div id="systematics-reading"><span class="status-label">Loading today's reading…</span></div>
      </div>
    </div>`;

    document.getElementById('sys-prev').onclick  = () => systematicsNav(-1);
    document.getElementById('sys-next').onclick  = () => systematicsNav(+1);
    document.getElementById('sys-today').onclick = () => { systematicsDate = new Date(); systematicsDate.setHours(0,0,0,0); systematicsRefresh(); };
    document.getElementById('sys-jump-select').onchange = (e) => {
        const day = parseInt(e.target.value);
        if (day) systematicsJumpToDay(day);
    };

    systematicsRefresh();
}

// Converts a day-of-year (1-365) to a Date in the year currently being
// viewed, using the same fixed non-leap reference as api/systematics.php's
// mapping in the other direction.
function systematicsJumpToDay(day) {
    const ref = new Date(2025, 0, day);
    const target = new Date(systematicsDate.getFullYear(), ref.getMonth(), ref.getDate());
    target.setHours(0, 0, 0, 0);
    systematicsDate = target;
    systematicsRefresh();
}

function systematicsNav(delta) {
    systematicsDate = new Date(systematicsDate.getTime() + delta * 86400000);
    systematicsRefresh();
}

function systematicsRefresh() {
    document.getElementById('sys-date-lbl').textContent = formatDateFull(systematicsDate);
    document.getElementById('systematics-reading').innerHTML = '<span class="status-label">Loading…</span>';
    loadSystematics();
}

async function loadSystematics() {
    const requestedDate = systematicsDate;
    try {
        const data = await api('systematics.php?date=' + dateToISO(requestedDate));
        if (requestedDate.getTime() !== systematicsDate.getTime()) return; // user navigated away
        renderSystematics(data);
    } catch (e) {
        if (requestedDate.getTime() !== systematicsDate.getTime()) return;
        document.getElementById('systematics-reading').textContent = 'Could not load reading: ' + e.message;
    }
}

function renderSystematics(data) {
    const container = document.getElementById('systematics-reading');
    if (!data.available) {
        container.innerHTML = `<span class="status-label">Day ${data.day} — this devotional hasn't been written yet.</span>`;
        return;
    }
    const s = data.sections || {};
    let html = `<div class="section-heading">${escapeHtml(data.section || '')}</div>
                <h2 class="systematics-title">${escapeHtml(data.title || '')}</h2>`;
    if (s['Verse']) {
        html += `<blockquote class="systematics-verse">${systematicsLiteToHtml(s['Verse'])}</blockquote>`;
    }
    ['Explanation', 'Prayer', 'Reflection Question'].forEach(key => {
        if (s[key]) {
            html += `<div class="systematics-section"><div class="section-heading">${escapeHtml(key)}</div>${systematicsLiteToHtml(s[key])}</div>`;
        }
    });
    container.innerHTML = html;
}

// The devotional Markdown only ever uses blank-line paragraphs and *italic*
// spans, so a tiny hand-rolled converter is enough — no Markdown library needed.
function systematicsLiteToHtml(text) {
    return text.split(/\n\s*\n/).map(para => {
        let html = escapeHtml(para.replace(/\s+/g, ' ').trim());
        html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
        return `<p>${html}</p>`;
    }).join('');
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

    const today = data.today || {};
    const current = el('div', { class: 'weather-current' },
        el('div', { class: 'weather-icon' }, data.icon || '🌡️'),
        el('div', { class: 'weather-temp' }, data.temp || '--°C'),
        el('div', { class: 'weather-desc' }, data.desc || ''),
        el('div', { class: 'weather-hilo' }, `H: ${today.hi || '--'}  L: ${today.lo || '--'}`),
    );
    box.appendChild(current);

    const d = data.details || {};
    const detailItems = [
        ['🤔', 'Feels like', d.feels_like],
        ['💧', 'Humidity',   d.humidity],
        ['💨', 'Wind',       d.wind],
        ['🌬️', 'Gusts',      d.wind_gusts],
        ['☔', 'Rain chance', today.rain_chance],
        ['🔆', 'UV index',   today.uv_index],
        ['🌅', 'Sunrise',    today.sunrise],
        ['🌇', 'Sunset',     today.sunset],
    ].filter(([, , v]) => v !== undefined && v !== null && v !== '--');

    if (detailItems.length) {
        const grid = el('div', { class: 'weather-details-grid' });
        for (const [icon, label, value] of detailItems) {
            grid.appendChild(el('div', { class: 'weather-detail-card' },
                el('div', { class: 'weather-detail-icon' }, icon),
                el('div', { class: 'weather-detail-value' }, String(value)),
                el('div', { class: 'weather-detail-label' }, label),
            ));
        }
        box.appendChild(grid);
    }

    if (data.hourly_forecast && data.hourly_forecast.length) {
        box.appendChild(el('span', { class: 'source-label' }, 'NEXT 12 HOURS'));
        const hourRow = el('div', { class: 'hourly-row' });
        for (const h of data.hourly_forecast) {
            hourRow.appendChild(el('div', { class: 'hourly-card' },
                el('div', { class: 'hourly-time' }, h.time),
                el('div', { class: 'hourly-icon' }, h.icon),
                el('div', { class: 'hourly-temp' }, h.temp),
                el('div', { class: 'hourly-rain' }, h.rain_chance),
            ));
        }
        box.appendChild(hourRow);
    }

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

/* ── DAILY BIBLE TAB ───────────────────────────────────────────────── */
// Generated by tools/gen_daily_plan.py — do not edit by hand.
// [label, [[bookId, chapter, fromVerse, toVerse], ...]]; null verses = whole chapter
const DAILY_NT_PLAN = [
    ["Matthew 1", [["MAT",1,1,25]]],
    ["Matthew 2", [["MAT",2,1,23]]],
    ["Matthew 3", [["MAT",3,1,17]]],
    ["Matthew 4", [["MAT",4,1,25]]],
    ["Matthew 5:1–20", [["MAT",5,1,20]]],
    ["Matthew 5:21–48", [["MAT",5,21,48]]],
    ["Matthew 6:1–18", [["MAT",6,1,18]]],
    ["Matthew 6:19–34", [["MAT",6,19,34]]],
    ["Matthew 7", [["MAT",7,1,29]]],
    ["Matthew 8:1–17", [["MAT",8,1,17]]],
    ["Matthew 8:18–34", [["MAT",8,18,34]]],
    ["Matthew 9:1–17", [["MAT",9,1,17]]],
    ["Matthew 9:18–38", [["MAT",9,18,38]]],
    ["Matthew 10:1–23", [["MAT",10,1,23]]],
    ["Matthew 10:24–42", [["MAT",10,24,42]]],
    ["Matthew 11", [["MAT",11,1,30]]],
    ["Matthew 12:1–21", [["MAT",12,1,21]]],
    ["Matthew 12:22–50", [["MAT",12,22,50]]],
    ["Matthew 13:1–23", [["MAT",13,1,23]]],
    ["Matthew 13:24–43", [["MAT",13,24,43]]],
    ["Matthew 13:44–14:12", [["MAT",13,44,58],["MAT",14,1,12]]],
    ["Matthew 14:13–36", [["MAT",14,13,36]]],
    ["Matthew 15:1–20", [["MAT",15,1,20]]],
    ["Matthew 15:21–39", [["MAT",15,21,39]]],
    ["Matthew 16", [["MAT",16,1,28]]],
    ["Matthew 17", [["MAT",17,1,27]]],
    ["Matthew 18:1–20", [["MAT",18,1,20]]],
    ["Matthew 18:21–19:15", [["MAT",18,21,35],["MAT",19,1,15]]],
    ["Matthew 19:16–30", [["MAT",19,16,30]]],
    ["Matthew 20:1–16", [["MAT",20,1,16]]],
    ["Matthew 20:17–34", [["MAT",20,17,34]]],
    ["Matthew 21:1–22", [["MAT",21,1,22]]],
    ["Matthew 21:23–46", [["MAT",21,23,46]]],
    ["Matthew 22:1–22", [["MAT",22,1,22]]],
    ["Matthew 22:23–46", [["MAT",22,23,46]]],
    ["Matthew 23:1–22", [["MAT",23,1,22]]],
    ["Matthew 23:23–39", [["MAT",23,23,39]]],
    ["Matthew 24:1–31", [["MAT",24,1,31]]],
    ["Matthew 24:32–51", [["MAT",24,32,51]]],
    ["Matthew 25:1–13", [["MAT",25,1,13]]],
    ["Matthew 25:14–30", [["MAT",25,14,30]]],
    ["Matthew 25:31–26:16", [["MAT",25,31,46],["MAT",26,1,16]]],
    ["Matthew 26:17–35", [["MAT",26,17,35]]],
    ["Matthew 26:36–56", [["MAT",26,36,56]]],
    ["Matthew 26:57–75", [["MAT",26,57,75]]],
    ["Matthew 27:1–26", [["MAT",27,1,26]]],
    ["Matthew 27:27–44", [["MAT",27,27,44]]],
    ["Matthew 27:45–66", [["MAT",27,45,66]]],
    ["Matthew 28", [["MAT",28,1,20]]],
    ["Mark 1:1–20", [["MRK",1,1,20]]],
    ["Mark 1:21–45", [["MRK",1,21,45]]],
    ["Mark 2:1–17", [["MRK",2,1,17]]],
    ["Mark 2:18–3:12", [["MRK",2,18,28],["MRK",3,1,12]]],
    ["Mark 3:13–35", [["MRK",3,13,35]]],
    ["Mark 4:1–20", [["MRK",4,1,20]]],
    ["Mark 4:21–41", [["MRK",4,21,41]]],
    ["Mark 5:1–20", [["MRK",5,1,20]]],
    ["Mark 5:21–43", [["MRK",5,21,43]]],
    ["Mark 6:1–13", [["MRK",6,1,13]]],
    ["Mark 6:14–29", [["MRK",6,14,29]]],
    ["Mark 6:30–56", [["MRK",6,30,56]]],
    ["Mark 7:1–23", [["MRK",7,1,23]]],
    ["Mark 7:24–8:10", [["MRK",7,24,37],["MRK",8,1,10]]],
    ["Mark 8:11–26", [["MRK",8,11,26]]],
    ["Mark 8:27–9:13", [["MRK",8,27,38],["MRK",9,1,13]]],
    ["Mark 9:14–37", [["MRK",9,14,37]]],
    ["Mark 9:38–10:16", [["MRK",9,38,50],["MRK",10,1,16]]],
    ["Mark 10:17–34", [["MRK",10,17,34]]],
    ["Mark 10:35–52", [["MRK",10,35,52]]],
    ["Mark 11:1–19", [["MRK",11,1,19]]],
    ["Mark 11:20–12:12", [["MRK",11,20,33],["MRK",12,1,12]]],
    ["Mark 12:13–34", [["MRK",12,13,34]]],
    ["Mark 12:35–13:13", [["MRK",12,35,44],["MRK",13,1,13]]],
    ["Mark 13:14–37", [["MRK",13,14,37]]],
    ["Mark 14:1–25", [["MRK",14,1,25]]],
    ["Mark 14:26–52", [["MRK",14,26,52]]],
    ["Mark 14:53–72", [["MRK",14,53,72]]],
    ["Mark 15:1–20", [["MRK",15,1,20]]],
    ["Mark 15:21–47", [["MRK",15,21,47]]],
    ["Mark 16", [["MRK",16,1,20]]],
    ["Luke 1:1–25", [["LUK",1,1,25]]],
    ["Luke 1:26–56", [["LUK",1,26,56]]],
    ["Luke 1:57–80", [["LUK",1,57,80]]],
    ["Luke 2:1–21", [["LUK",2,1,21]]],
    ["Luke 2:22–40", [["LUK",2,22,40]]],
    ["Luke 2:41–52", [["LUK",2,41,52]]],
    ["Luke 3:1–22", [["LUK",3,1,22]]],
    ["Luke 3:23–4:13", [["LUK",3,23,38],["LUK",4,1,13]]],
    ["Luke 4:14–30", [["LUK",4,14,30]]],
    ["Luke 4:31–44", [["LUK",4,31,44]]],
    ["Luke 5:1–26", [["LUK",5,1,26]]],
    ["Luke 5:27–6:16", [["LUK",5,27,39],["LUK",6,1,16]]],
    ["Luke 6:17–38", [["LUK",6,17,38]]],
    ["Luke 6:39–7:17", [["LUK",6,39,49],["LUK",7,1,17]]],
    ["Luke 7:18–35", [["LUK",7,18,35]]],
    ["Luke 7:36–8:3", [["LUK",7,36,50],["LUK",8,1,3]]],
    ["Luke 8:4–21", [["LUK",8,4,21]]],
    ["Luke 8:22–39", [["LUK",8,22,39]]],
    ["Luke 8:40–56", [["LUK",8,40,56]]],
    ["Luke 9:1–17", [["LUK",9,1,17]]],
    ["Luke 9:18–36", [["LUK",9,18,36]]],
    ["Luke 9:37–62", [["LUK",9,37,62]]],
    ["Luke 10:1–24", [["LUK",10,1,24]]],
    ["Luke 10:25–42", [["LUK",10,25,42]]],
    ["Luke 11:1–28", [["LUK",11,1,28]]],
    ["Luke 11:29–54", [["LUK",11,29,54]]],
    ["Luke 12:1–21", [["LUK",12,1,21]]],
    ["Luke 12:22–48", [["LUK",12,22,48]]],
    ["Luke 12:49–13:9", [["LUK",12,49,59],["LUK",13,1,9]]],
    ["Luke 13:10–35", [["LUK",13,10,35]]],
    ["Luke 14:1–24", [["LUK",14,1,24]]],
    ["Luke 14:25–15:10", [["LUK",14,25,35],["LUK",15,1,10]]],
    ["Luke 15:11–32", [["LUK",15,11,32]]],
    ["Luke 16:1–18", [["LUK",16,1,18]]],
    ["Luke 16:19–17:10", [["LUK",16,19,31],["LUK",17,1,10]]],
    ["Luke 17:11–37", [["LUK",17,11,37]]],
    ["Luke 18:1–17", [["LUK",18,1,17]]],
    ["Luke 18:18–43", [["LUK",18,18,43]]],
    ["Luke 19:1–27", [["LUK",19,1,27]]],
    ["Luke 19:28–48", [["LUK",19,28,48]]],
    ["Luke 20:1–26", [["LUK",20,1,26]]],
    ["Luke 20:27–47", [["LUK",20,27,47]]],
    ["Luke 21:1–19", [["LUK",21,1,19]]],
    ["Luke 21:20–38", [["LUK",21,20,38]]],
    ["Luke 22:1–23", [["LUK",22,1,23]]],
    ["Luke 22:24–46", [["LUK",22,24,46]]],
    ["Luke 22:47–71", [["LUK",22,47,71]]],
    ["Luke 23:1–25", [["LUK",23,1,25]]],
    ["Luke 23:26–43", [["LUK",23,26,43]]],
    ["Luke 23:44–24:12", [["LUK",23,44,56],["LUK",24,1,12]]],
    ["Luke 24:13–35", [["LUK",24,13,35]]],
    ["Luke 24:36–53", [["LUK",24,36,53]]],
    ["John 1:1–18", [["JHN",1,1,18]]],
    ["John 1:19–34", [["JHN",1,19,34]]],
    ["John 1:35–51", [["JHN",1,35,51]]],
    ["John 2", [["JHN",2,1,25]]],
    ["John 3:1–21", [["JHN",3,1,21]]],
    ["John 3:22–36", [["JHN",3,22,36]]],
    ["John 4:1–26", [["JHN",4,1,26]]],
    ["John 4:27–54", [["JHN",4,27,54]]],
    ["John 5:1–18", [["JHN",5,1,18]]],
    ["John 5:19–47", [["JHN",5,19,47]]],
    ["John 6:1–21", [["JHN",6,1,21]]],
    ["John 6:22–40", [["JHN",6,22,40]]],
    ["John 6:41–59", [["JHN",6,41,59]]],
    ["John 6:60–71", [["JHN",6,60,71]]],
    ["John 7:1–24", [["JHN",7,1,24]]],
    ["John 7:25–52", [["JHN",7,25,52]]],
    ["John 7:53–8:20", [["JHN",7,53,53],["JHN",8,1,20]]],
    ["John 8:21–47", [["JHN",8,21,47]]],
    ["John 8:48–9:12", [["JHN",8,48,59],["JHN",9,1,12]]],
    ["John 9:13–41", [["JHN",9,13,41]]],
    ["John 10:1–21", [["JHN",10,1,21]]],
    ["John 10:22–42", [["JHN",10,22,42]]],
    ["John 11:1–27", [["JHN",11,1,27]]],
    ["John 11:28–57", [["JHN",11,28,57]]],
    ["John 12:1–19", [["JHN",12,1,19]]],
    ["John 12:20–50", [["JHN",12,20,50]]],
    ["John 13:1–20", [["JHN",13,1,20]]],
    ["John 13:21–38", [["JHN",13,21,38]]],
    ["John 14:1–14", [["JHN",14,1,14]]],
    ["John 14:15–31", [["JHN",14,15,31]]],
    ["John 15", [["JHN",15,1,27]]],
    ["John 16:1–15", [["JHN",16,1,15]]],
    ["John 16:16–33", [["JHN",16,16,33]]],
    ["John 17", [["JHN",17,1,26]]],
    ["John 18:1–27", [["JHN",18,1,27]]],
    ["John 18:28–19:16", [["JHN",18,28,40],["JHN",19,1,16]]],
    ["John 19:17–42", [["JHN",19,17,42]]],
    ["John 20", [["JHN",20,1,31]]],
    ["John 21", [["JHN",21,1,25]]],
    ["Acts 1", [["ACT",1,1,26]]],
    ["Acts 2:1–21", [["ACT",2,1,21]]],
    ["Acts 2:22–47", [["ACT",2,22,47]]],
    ["Acts 3", [["ACT",3,1,26]]],
    ["Acts 4:1–22", [["ACT",4,1,22]]],
    ["Acts 4:23–5:11", [["ACT",4,23,37],["ACT",5,1,11]]],
    ["Acts 5:12–42", [["ACT",5,12,42]]],
    ["Acts 6", [["ACT",6,1,15]]],
    ["Acts 7:1–29", [["ACT",7,1,29]]],
    ["Acts 7:30–60", [["ACT",7,30,60]]],
    ["Acts 8:1–25", [["ACT",8,1,25]]],
    ["Acts 8:26–40", [["ACT",8,26,40]]],
    ["Acts 9:1–19", [["ACT",9,1,19]]],
    ["Acts 9:20–43", [["ACT",9,20,43]]],
    ["Acts 10:1–23", [["ACT",10,1,23]]],
    ["Acts 10:24–48", [["ACT",10,24,48]]],
    ["Acts 11:1–18", [["ACT",11,1,18]]],
    ["Acts 11:19–12:5", [["ACT",11,19,30],["ACT",12,1,5]]],
    ["Acts 12:6–25", [["ACT",12,6,25]]],
    ["Acts 13:1–25", [["ACT",13,1,25]]],
    ["Acts 13:26–52", [["ACT",13,26,52]]],
    ["Acts 14", [["ACT",14,1,28]]],
    ["Acts 15:1–21", [["ACT",15,1,21]]],
    ["Acts 15:22–41", [["ACT",15,22,41]]],
    ["Acts 16:1–15", [["ACT",16,1,15]]],
    ["Acts 16:16–40", [["ACT",16,16,40]]],
    ["Acts 17:1–15", [["ACT",17,1,15]]],
    ["Acts 17:16–34", [["ACT",17,16,34]]],
    ["Acts 18", [["ACT",18,1,28]]],
    ["Acts 19:1–20", [["ACT",19,1,20]]],
    ["Acts 19:21–41", [["ACT",19,21,41]]],
    ["Acts 20:1–16", [["ACT",20,1,16]]],
    ["Acts 20:17–38", [["ACT",20,17,38]]],
    ["Acts 21:1–16", [["ACT",21,1,16]]],
    ["Acts 21:17–40", [["ACT",21,17,40]]],
    ["Acts 22", [["ACT",22,1,30]]],
    ["Acts 23:1–22", [["ACT",23,1,22]]],
    ["Acts 23:23–24:9", [["ACT",23,23,35],["ACT",24,1,9]]],
    ["Acts 24:10–27", [["ACT",24,10,27]]],
    ["Acts 25", [["ACT",25,1,27]]],
    ["Acts 26:1–18", [["ACT",26,1,18]]],
    ["Acts 26:19–32", [["ACT",26,19,32]]],
    ["Acts 27:1–26", [["ACT",27,1,26]]],
    ["Acts 27:27–44", [["ACT",27,27,44]]],
    ["Acts 28", [["ACT",28,1,31]]],
    ["Romans 1:1–17", [["ROM",1,1,17]]],
    ["Romans 1:18–32", [["ROM",1,18,32]]],
    ["Romans 2", [["ROM",2,1,29]]],
    ["Romans 3:1–20", [["ROM",3,1,20]]],
    ["Romans 3:21–4:12", [["ROM",3,21,31],["ROM",4,1,12]]],
    ["Romans 4:13–5:11", [["ROM",4,13,25],["ROM",5,1,11]]],
    ["Romans 5:12–6:14", [["ROM",5,12,21],["ROM",6,1,14]]],
    ["Romans 6:15–7:6", [["ROM",6,15,23],["ROM",7,1,6]]],
    ["Romans 7:7–25", [["ROM",7,7,25]]],
    ["Romans 8:1–17", [["ROM",8,1,17]]],
    ["Romans 8:18–39", [["ROM",8,18,39]]],
    ["Romans 9:1–29", [["ROM",9,1,29]]],
    ["Romans 9:30–10:21", [["ROM",9,30,33],["ROM",10,1,21]]],
    ["Romans 11:1–24", [["ROM",11,1,24]]],
    ["Romans 11:25–12:8", [["ROM",11,25,36],["ROM",12,1,8]]],
    ["Romans 12:9–13:14", [["ROM",12,9,21],["ROM",13,1,14]]],
    ["Romans 14", [["ROM",14,1,23]]],
    ["Romans 15:1–13", [["ROM",15,1,13]]],
    ["Romans 15:14–33", [["ROM",15,14,33]]],
    ["Romans 16", [["ROM",16,1,27]]],
    ["1 Corinthians 1:1–17", [["1CO",1,1,17]]],
    ["1 Corinthians 1:18–2:5", [["1CO",1,18,31],["1CO",2,1,5]]],
    ["1 Corinthians 2:6–3:9", [["1CO",2,6,16],["1CO",3,1,9]]],
    ["1 Corinthians 3:10–23", [["1CO",3,10,23]]],
    ["1 Corinthians 4", [["1CO",4,1,21]]],
    ["1 Corinthians 5:1–6:11", [["1CO",5,1,13],["1CO",6,1,11]]],
    ["1 Corinthians 6:12–7:16", [["1CO",6,12,20],["1CO",7,1,16]]],
    ["1 Corinthians 7:17–40", [["1CO",7,17,40]]],
    ["1 Corinthians 8:1–9:14", [["1CO",8,1,13],["1CO",9,1,14]]],
    ["1 Corinthians 9:15–10:13", [["1CO",9,15,27],["1CO",10,1,13]]],
    ["1 Corinthians 10:14–11:1", [["1CO",10,14,33],["1CO",11,1,1]]],
    ["1 Corinthians 11:2–16", [["1CO",11,2,16]]],
    ["1 Corinthians 11:17–34", [["1CO",11,17,34]]],
    ["1 Corinthians 12", [["1CO",12,1,31]]],
    ["1 Corinthians 13", [["1CO",13,1,13]]],
    ["1 Corinthians 14:1–25", [["1CO",14,1,25]]],
    ["1 Corinthians 14:26–40", [["1CO",14,26,40]]],
    ["1 Corinthians 15:1–19", [["1CO",15,1,19]]],
    ["1 Corinthians 15:20–34", [["1CO",15,20,34]]],
    ["1 Corinthians 15:35–58", [["1CO",15,35,58]]],
    ["1 Corinthians 16", [["1CO",16,1,24]]],
    ["2 Corinthians 1", [["2CO",1,1,24]]],
    ["2 Corinthians 2", [["2CO",2,1,17]]],
    ["2 Corinthians 3", [["2CO",3,1,18]]],
    ["2 Corinthians 4", [["2CO",4,1,18]]],
    ["2 Corinthians 5", [["2CO",5,1,21]]],
    ["2 Corinthians 6:1–7:1", [["2CO",6,1,18],["2CO",7,1,1]]],
    ["2 Corinthians 7:2–16", [["2CO",7,2,16]]],
    ["2 Corinthians 8", [["2CO",8,1,24]]],
    ["2 Corinthians 9", [["2CO",9,1,15]]],
    ["2 Corinthians 10", [["2CO",10,1,18]]],
    ["2 Corinthians 11:1–15", [["2CO",11,1,15]]],
    ["2 Corinthians 11:16–12:10", [["2CO",11,16,33],["2CO",12,1,10]]],
    ["2 Corinthians 12:11–13:14", [["2CO",12,11,21],["2CO",13,1,14]]],
    ["Galatians 1", [["GAL",1,1,24]]],
    ["Galatians 2", [["GAL",2,1,21]]],
    ["Galatians 3:1–14", [["GAL",3,1,14]]],
    ["Galatians 3:15–29", [["GAL",3,15,29]]],
    ["Galatians 4", [["GAL",4,1,31]]],
    ["Galatians 5", [["GAL",5,1,26]]],
    ["Galatians 6", [["GAL",6,1,18]]],
    ["Ephesians 1", [["EPH",1,1,23]]],
    ["Ephesians 2", [["EPH",2,1,22]]],
    ["Ephesians 3", [["EPH",3,1,21]]],
    ["Ephesians 4:1–16", [["EPH",4,1,16]]],
    ["Ephesians 4:17–32", [["EPH",4,17,32]]],
    ["Ephesians 5", [["EPH",5,1,33]]],
    ["Ephesians 6", [["EPH",6,1,24]]],
    ["Philippians 1:1–11", [["PHP",1,1,11]]],
    ["Philippians 1:12–30", [["PHP",1,12,30]]],
    ["Philippians 2", [["PHP",2,1,30]]],
    ["Philippians 3", [["PHP",3,1,21]]],
    ["Philippians 4", [["PHP",4,1,23]]],
    ["Colossians 1:1–23", [["COL",1,1,23]]],
    ["Colossians 1:24–2:23", [["COL",1,24,29],["COL",2,1,23]]],
    ["Colossians 3:1–4:1", [["COL",3,1,25],["COL",4,1,1]]],
    ["Colossians 4:2–18", [["COL",4,2,18]]],
    ["1 Thessalonians 1:1–2:16", [["1TH",1,1,10],["1TH",2,1,16]]],
    ["1 Thessalonians 2:17–3:13", [["1TH",2,17,20],["1TH",3,1,13]]],
    ["1 Thessalonians 4", [["1TH",4,1,18]]],
    ["1 Thessalonians 5", [["1TH",5,1,28]]],
    ["2 Thessalonians 1:1–2:17", [["2TH",1,1,12],["2TH",2,1,17]]],
    ["2 Thessalonians 3", [["2TH",3,1,18]]],
    ["1 Timothy 1", [["1TI",1,1,20]]],
    ["1 Timothy 2:1–3:16", [["1TI",2,1,15],["1TI",3,1,16]]],
    ["1 Timothy 4", [["1TI",4,1,16]]],
    ["1 Timothy 5", [["1TI",5,1,25]]],
    ["1 Timothy 6", [["1TI",6,1,21]]],
    ["2 Timothy 1", [["2TI",1,1,18]]],
    ["2 Timothy 2", [["2TI",2,1,26]]],
    ["2 Timothy 3", [["2TI",3,1,17]]],
    ["2 Timothy 4", [["2TI",4,1,22]]],
    ["Titus 1", [["TIT",1,1,16]]],
    ["Titus 2:1–3:15", [["TIT",2,1,15],["TIT",3,1,15]]],
    ["Philemon", [["PHM",1,1,25]]],
    ["Hebrews 1", [["HEB",1,1,14]]],
    ["Hebrews 2", [["HEB",2,1,18]]],
    ["Hebrews 3", [["HEB",3,1,19]]],
    ["Hebrews 4", [["HEB",4,1,16]]],
    ["Hebrews 5", [["HEB",5,1,14]]],
    ["Hebrews 6", [["HEB",6,1,20]]],
    ["Hebrews 7", [["HEB",7,1,28]]],
    ["Hebrews 8", [["HEB",8,1,13]]],
    ["Hebrews 9", [["HEB",9,1,28]]],
    ["Hebrews 10:1–18", [["HEB",10,1,18]]],
    ["Hebrews 10:19–39", [["HEB",10,19,39]]],
    ["Hebrews 11:1–22", [["HEB",11,1,22]]],
    ["Hebrews 11:23–40", [["HEB",11,23,40]]],
    ["Hebrews 12", [["HEB",12,1,29]]],
    ["Hebrews 13", [["HEB",13,1,25]]],
    ["James 1", [["JAS",1,1,27]]],
    ["James 2", [["JAS",2,1,26]]],
    ["James 3", [["JAS",3,1,18]]],
    ["James 4", [["JAS",4,1,17]]],
    ["James 5", [["JAS",5,1,20]]],
    ["1 Peter 1", [["1PE",1,1,25]]],
    ["1 Peter 2", [["1PE",2,1,25]]],
    ["1 Peter 3", [["1PE",3,1,22]]],
    ["1 Peter 4", [["1PE",4,1,19]]],
    ["1 Peter 5", [["1PE",5,1,14]]],
    ["2 Peter 1", [["2PE",1,1,21]]],
    ["2 Peter 2", [["2PE",2,1,22]]],
    ["2 Peter 3", [["2PE",3,1,18]]],
    ["1 John 1:1–2:6", [["1JN",1,1,10],["1JN",2,1,6]]],
    ["1 John 2:7–29", [["1JN",2,7,29]]],
    ["1 John 3", [["1JN",3,1,24]]],
    ["1 John 4", [["1JN",4,1,21]]],
    ["1 John 5", [["1JN",5,1,21]]],
    ["2 John; 3 John", [["2JN",1,1,13],["3JN",1,1,14]]],
    ["Jude", [["JUD",1,1,25]]],
    ["Revelation 1", [["REV",1,1,20]]],
    ["Revelation 2", [["REV",2,1,29]]],
    ["Revelation 3", [["REV",3,1,22]]],
    ["Revelation 4:1–5:14", [["REV",4,1,11],["REV",5,1,14]]],
    ["Revelation 6", [["REV",6,1,17]]],
    ["Revelation 7", [["REV",7,1,17]]],
    ["Revelation 8:1–9:12", [["REV",8,1,13],["REV",9,1,12]]],
    ["Revelation 9:13–10:11", [["REV",9,13,21],["REV",10,1,11]]],
    ["Revelation 11", [["REV",11,1,19]]],
    ["Revelation 12", [["REV",12,1,17]]],
    ["Revelation 13", [["REV",13,1,18]]],
    ["Revelation 14", [["REV",14,1,20]]],
    ["Revelation 15:1–16:21", [["REV",15,1,8],["REV",16,1,21]]],
    ["Revelation 17", [["REV",17,1,18]]],
    ["Revelation 18", [["REV",18,1,24]]],
    ["Revelation 19", [["REV",19,1,21]]],
    ["Revelation 20", [["REV",20,1,15]]],
    ["Revelation 21", [["REV",21,1,27]]],
    ["Revelation 22", [["REV",22,1,21]]],
];
const DAILY_PSALM_PLAN = [
    ["Psalm 1", [["PSA",1,null,null]]],
    ["Psalm 2", [["PSA",2,null,null]]],
    ["Psalm 3", [["PSA",3,null,null]]],
    ["Psalm 4", [["PSA",4,null,null]]],
    ["Psalm 5", [["PSA",5,null,null]]],
    ["Psalm 6", [["PSA",6,null,null]]],
    ["Psalm 7", [["PSA",7,null,null]]],
    ["Psalm 8", [["PSA",8,null,null]]],
    ["Psalm 9", [["PSA",9,null,null]]],
    ["Psalm 10", [["PSA",10,null,null]]],
    ["Psalm 11", [["PSA",11,null,null]]],
    ["Psalm 12", [["PSA",12,null,null]]],
    ["Psalm 13", [["PSA",13,null,null]]],
    ["Psalm 14", [["PSA",14,null,null]]],
    ["Psalm 15", [["PSA",15,null,null]]],
    ["Psalm 16", [["PSA",16,null,null]]],
    ["Psalm 17", [["PSA",17,null,null]]],
    ["Psalm 18", [["PSA",18,null,null]]],
    ["Psalm 19", [["PSA",19,null,null]]],
    ["Psalm 20", [["PSA",20,null,null]]],
    ["Psalm 21", [["PSA",21,null,null]]],
    ["Psalm 22", [["PSA",22,null,null]]],
    ["Psalm 23", [["PSA",23,null,null]]],
    ["Psalm 24", [["PSA",24,null,null]]],
    ["Psalm 25", [["PSA",25,null,null]]],
    ["Psalm 26", [["PSA",26,null,null]]],
    ["Psalm 27", [["PSA",27,null,null]]],
    ["Psalm 28", [["PSA",28,null,null]]],
    ["Psalm 29", [["PSA",29,null,null]]],
    ["Psalm 30", [["PSA",30,null,null]]],
    ["Psalm 31", [["PSA",31,null,null]]],
    ["Psalm 32", [["PSA",32,null,null]]],
    ["Psalm 33", [["PSA",33,null,null]]],
    ["Psalm 34", [["PSA",34,null,null]]],
    ["Psalm 35", [["PSA",35,null,null]]],
    ["Psalm 36", [["PSA",36,null,null]]],
    ["Psalm 37", [["PSA",37,null,null]]],
    ["Psalm 38", [["PSA",38,null,null]]],
    ["Psalm 39", [["PSA",39,null,null]]],
    ["Psalm 40", [["PSA",40,null,null]]],
    ["Psalm 41", [["PSA",41,null,null]]],
    ["Psalm 42", [["PSA",42,null,null]]],
    ["Psalm 43", [["PSA",43,null,null]]],
    ["Psalm 44", [["PSA",44,null,null]]],
    ["Psalm 45", [["PSA",45,null,null]]],
    ["Psalm 46", [["PSA",46,null,null]]],
    ["Psalm 47", [["PSA",47,null,null]]],
    ["Psalm 48", [["PSA",48,null,null]]],
    ["Psalm 49", [["PSA",49,null,null]]],
    ["Psalm 50", [["PSA",50,null,null]]],
    ["Psalm 51", [["PSA",51,null,null]]],
    ["Psalm 52", [["PSA",52,null,null]]],
    ["Psalm 53", [["PSA",53,null,null]]],
    ["Psalm 54", [["PSA",54,null,null]]],
    ["Psalm 55", [["PSA",55,null,null]]],
    ["Psalm 56", [["PSA",56,null,null]]],
    ["Psalm 57", [["PSA",57,null,null]]],
    ["Psalm 58", [["PSA",58,null,null]]],
    ["Psalm 59", [["PSA",59,null,null]]],
    ["Psalm 60", [["PSA",60,null,null]]],
    ["Psalm 61", [["PSA",61,null,null]]],
    ["Psalm 62", [["PSA",62,null,null]]],
    ["Psalm 63", [["PSA",63,null,null]]],
    ["Psalm 64", [["PSA",64,null,null]]],
    ["Psalm 65", [["PSA",65,null,null]]],
    ["Psalm 66", [["PSA",66,null,null]]],
    ["Psalm 67", [["PSA",67,null,null]]],
    ["Psalm 68", [["PSA",68,null,null]]],
    ["Psalm 69", [["PSA",69,null,null]]],
    ["Psalm 70", [["PSA",70,null,null]]],
    ["Psalm 71", [["PSA",71,null,null]]],
    ["Psalm 72", [["PSA",72,null,null]]],
    ["Psalm 73", [["PSA",73,null,null]]],
    ["Psalm 74", [["PSA",74,null,null]]],
    ["Psalm 75", [["PSA",75,null,null]]],
    ["Psalm 76", [["PSA",76,null,null]]],
    ["Psalm 77", [["PSA",77,null,null]]],
    ["Psalm 78", [["PSA",78,null,null]]],
    ["Psalm 79", [["PSA",79,null,null]]],
    ["Psalm 80", [["PSA",80,null,null]]],
    ["Psalm 81", [["PSA",81,null,null]]],
    ["Psalm 82", [["PSA",82,null,null]]],
    ["Psalm 83", [["PSA",83,null,null]]],
    ["Psalm 84", [["PSA",84,null,null]]],
    ["Psalm 85", [["PSA",85,null,null]]],
    ["Psalm 86", [["PSA",86,null,null]]],
    ["Psalm 87", [["PSA",87,null,null]]],
    ["Psalm 88", [["PSA",88,null,null]]],
    ["Psalm 89", [["PSA",89,null,null]]],
    ["Psalm 90", [["PSA",90,null,null]]],
    ["Psalm 91", [["PSA",91,null,null]]],
    ["Psalm 92", [["PSA",92,null,null]]],
    ["Psalm 93", [["PSA",93,null,null]]],
    ["Psalm 94", [["PSA",94,null,null]]],
    ["Psalm 95", [["PSA",95,null,null]]],
    ["Psalm 96", [["PSA",96,null,null]]],
    ["Psalm 97", [["PSA",97,null,null]]],
    ["Psalm 98", [["PSA",98,null,null]]],
    ["Psalm 99", [["PSA",99,null,null]]],
    ["Psalm 100", [["PSA",100,null,null]]],
    ["Psalm 101", [["PSA",101,null,null]]],
    ["Psalm 102", [["PSA",102,null,null]]],
    ["Psalm 103", [["PSA",103,null,null]]],
    ["Psalm 104", [["PSA",104,null,null]]],
    ["Psalm 105", [["PSA",105,null,null]]],
    ["Psalm 106", [["PSA",106,null,null]]],
    ["Psalm 107", [["PSA",107,null,null]]],
    ["Psalm 108", [["PSA",108,null,null]]],
    ["Psalm 109", [["PSA",109,null,null]]],
    ["Psalm 110", [["PSA",110,null,null]]],
    ["Psalm 111", [["PSA",111,null,null]]],
    ["Psalm 112", [["PSA",112,null,null]]],
    ["Psalm 113", [["PSA",113,null,null]]],
    ["Psalm 114", [["PSA",114,null,null]]],
    ["Psalm 115", [["PSA",115,null,null]]],
    ["Psalm 116", [["PSA",116,null,null]]],
    ["Psalm 117", [["PSA",117,null,null]]],
    ["Psalm 118", [["PSA",118,null,null]]],
    ["Psalm 119:1–48", [["PSA",119,1,48]]],
    ["Psalm 119:49–96", [["PSA",119,49,96]]],
    ["Psalm 119:97–136", [["PSA",119,97,136]]],
    ["Psalm 119:137–176", [["PSA",119,137,176]]],
    ["Psalm 120", [["PSA",120,null,null]]],
    ["Psalm 121", [["PSA",121,null,null]]],
    ["Psalm 122", [["PSA",122,null,null]]],
    ["Psalm 123", [["PSA",123,null,null]]],
    ["Psalm 124", [["PSA",124,null,null]]],
    ["Psalm 125", [["PSA",125,null,null]]],
    ["Psalm 126", [["PSA",126,null,null]]],
    ["Psalm 127", [["PSA",127,null,null]]],
    ["Psalm 128", [["PSA",128,null,null]]],
    ["Psalm 129", [["PSA",129,null,null]]],
    ["Psalm 130", [["PSA",130,null,null]]],
    ["Psalm 131", [["PSA",131,null,null]]],
    ["Psalm 132", [["PSA",132,null,null]]],
    ["Psalm 133", [["PSA",133,null,null]]],
    ["Psalm 134", [["PSA",134,null,null]]],
    ["Psalm 135", [["PSA",135,null,null]]],
    ["Psalm 136", [["PSA",136,null,null]]],
    ["Psalm 137", [["PSA",137,null,null]]],
    ["Psalm 138", [["PSA",138,null,null]]],
    ["Psalm 139", [["PSA",139,null,null]]],
    ["Psalm 140", [["PSA",140,null,null]]],
    ["Psalm 141", [["PSA",141,null,null]]],
    ["Psalm 142", [["PSA",142,null,null]]],
    ["Psalm 143", [["PSA",143,null,null]]],
    ["Psalm 144", [["PSA",144,null,null]]],
    ["Psalm 145", [["PSA",145,null,null]]],
    ["Psalm 146", [["PSA",146,null,null]]],
    ["Psalm 147", [["PSA",147,null,null]]],
    ["Psalm 148", [["PSA",148,null,null]]],
    ["Psalm 149", [["PSA",149,null,null]]],
    ["Psalm 150", [["PSA",150,null,null]]],
];
const DAILY_PROV_PLAN = [
    ["Proverbs 1:1–3", [["PRO",1,1,3]]],
    ["Proverbs 1:4–6", [["PRO",1,4,6]]],
    ["Proverbs 1:7–9", [["PRO",1,7,9]]],
    ["Proverbs 1:10–12", [["PRO",1,10,12]]],
    ["Proverbs 1:13–15", [["PRO",1,13,15]]],
    ["Proverbs 1:16–18", [["PRO",1,16,18]]],
    ["Proverbs 1:19–21", [["PRO",1,19,21]]],
    ["Proverbs 1:22–23", [["PRO",1,22,23]]],
    ["Proverbs 1:24–25", [["PRO",1,24,25]]],
    ["Proverbs 1:26–27", [["PRO",1,26,27]]],
    ["Proverbs 1:28–29", [["PRO",1,28,29]]],
    ["Proverbs 1:30–31", [["PRO",1,30,31]]],
    ["Proverbs 1:32–33", [["PRO",1,32,33]]],
    ["Proverbs 2:1–3", [["PRO",2,1,3]]],
    ["Proverbs 2:4–6", [["PRO",2,4,6]]],
    ["Proverbs 2:7–9", [["PRO",2,7,9]]],
    ["Proverbs 2:10–12", [["PRO",2,10,12]]],
    ["Proverbs 2:13–14", [["PRO",2,13,14]]],
    ["Proverbs 2:15–16", [["PRO",2,15,16]]],
    ["Proverbs 2:17–18", [["PRO",2,17,18]]],
    ["Proverbs 2:19–20", [["PRO",2,19,20]]],
    ["Proverbs 2:21–22", [["PRO",2,21,22]]],
    ["Proverbs 3:1–3", [["PRO",3,1,3]]],
    ["Proverbs 3:4–6", [["PRO",3,4,6]]],
    ["Proverbs 3:7–9", [["PRO",3,7,9]]],
    ["Proverbs 3:10–12", [["PRO",3,10,12]]],
    ["Proverbs 3:13–15", [["PRO",3,13,15]]],
    ["Proverbs 3:16–18", [["PRO",3,16,18]]],
    ["Proverbs 3:19–21", [["PRO",3,19,21]]],
    ["Proverbs 3:22–23", [["PRO",3,22,23]]],
    ["Proverbs 3:24–25", [["PRO",3,24,25]]],
    ["Proverbs 3:26–27", [["PRO",3,26,27]]],
    ["Proverbs 3:28–29", [["PRO",3,28,29]]],
    ["Proverbs 3:30–31", [["PRO",3,30,31]]],
    ["Proverbs 3:32–33", [["PRO",3,32,33]]],
    ["Proverbs 3:34–35", [["PRO",3,34,35]]],
    ["Proverbs 4:1–3", [["PRO",4,1,3]]],
    ["Proverbs 4:4–6", [["PRO",4,4,6]]],
    ["Proverbs 4:7–9", [["PRO",4,7,9]]],
    ["Proverbs 4:10–12", [["PRO",4,10,12]]],
    ["Proverbs 4:13–15", [["PRO",4,13,15]]],
    ["Proverbs 4:16–17", [["PRO",4,16,17]]],
    ["Proverbs 4:18–19", [["PRO",4,18,19]]],
    ["Proverbs 4:20–21", [["PRO",4,20,21]]],
    ["Proverbs 4:22–23", [["PRO",4,22,23]]],
    ["Proverbs 4:24–25", [["PRO",4,24,25]]],
    ["Proverbs 4:26–27", [["PRO",4,26,27]]],
    ["Proverbs 5:1–3", [["PRO",5,1,3]]],
    ["Proverbs 5:4–6", [["PRO",5,4,6]]],
    ["Proverbs 5:7–9", [["PRO",5,7,9]]],
    ["Proverbs 5:10–12", [["PRO",5,10,12]]],
    ["Proverbs 5:13–15", [["PRO",5,13,15]]],
    ["Proverbs 5:16–17", [["PRO",5,16,17]]],
    ["Proverbs 5:18–19", [["PRO",5,18,19]]],
    ["Proverbs 5:20–21", [["PRO",5,20,21]]],
    ["Proverbs 5:22–23", [["PRO",5,22,23]]],
    ["Proverbs 6:1–3", [["PRO",6,1,3]]],
    ["Proverbs 6:4–6", [["PRO",6,4,6]]],
    ["Proverbs 6:7–9", [["PRO",6,7,9]]],
    ["Proverbs 6:10–12", [["PRO",6,10,12]]],
    ["Proverbs 6:13–15", [["PRO",6,13,15]]],
    ["Proverbs 6:16–18", [["PRO",6,16,18]]],
    ["Proverbs 6:19–21", [["PRO",6,19,21]]],
    ["Proverbs 6:22–23", [["PRO",6,22,23]]],
    ["Proverbs 6:24–25", [["PRO",6,24,25]]],
    ["Proverbs 6:26–27", [["PRO",6,26,27]]],
    ["Proverbs 6:28–29", [["PRO",6,28,29]]],
    ["Proverbs 6:30–31", [["PRO",6,30,31]]],
    ["Proverbs 6:32–33", [["PRO",6,32,33]]],
    ["Proverbs 6:34–35", [["PRO",6,34,35]]],
    ["Proverbs 7:1–3", [["PRO",7,1,3]]],
    ["Proverbs 7:4–6", [["PRO",7,4,6]]],
    ["Proverbs 7:7–9", [["PRO",7,7,9]]],
    ["Proverbs 7:10–12", [["PRO",7,10,12]]],
    ["Proverbs 7:13–15", [["PRO",7,13,15]]],
    ["Proverbs 7:16–17", [["PRO",7,16,17]]],
    ["Proverbs 7:18–19", [["PRO",7,18,19]]],
    ["Proverbs 7:20–21", [["PRO",7,20,21]]],
    ["Proverbs 7:22–23", [["PRO",7,22,23]]],
    ["Proverbs 7:24–25", [["PRO",7,24,25]]],
    ["Proverbs 7:26–27", [["PRO",7,26,27]]],
    ["Proverbs 8:1–3", [["PRO",8,1,3]]],
    ["Proverbs 8:4–6", [["PRO",8,4,6]]],
    ["Proverbs 8:7–9", [["PRO",8,7,9]]],
    ["Proverbs 8:10–12", [["PRO",8,10,12]]],
    ["Proverbs 8:13–15", [["PRO",8,13,15]]],
    ["Proverbs 8:16–18", [["PRO",8,16,18]]],
    ["Proverbs 8:19–21", [["PRO",8,19,21]]],
    ["Proverbs 8:22–24", [["PRO",8,22,24]]],
    ["Proverbs 8:25–26", [["PRO",8,25,26]]],
    ["Proverbs 8:27–28", [["PRO",8,27,28]]],
    ["Proverbs 8:29–30", [["PRO",8,29,30]]],
    ["Proverbs 8:31–32", [["PRO",8,31,32]]],
    ["Proverbs 8:33–34", [["PRO",8,33,34]]],
    ["Proverbs 8:35–36", [["PRO",8,35,36]]],
    ["Proverbs 9:1–3", [["PRO",9,1,3]]],
    ["Proverbs 9:4–6", [["PRO",9,4,6]]],
    ["Proverbs 9:7–9", [["PRO",9,7,9]]],
    ["Proverbs 9:10–12", [["PRO",9,10,12]]],
    ["Proverbs 9:13–14", [["PRO",9,13,14]]],
    ["Proverbs 9:15–16", [["PRO",9,15,16]]],
    ["Proverbs 9:17–18", [["PRO",9,17,18]]],
    ["Proverbs 10:1–3", [["PRO",10,1,3]]],
    ["Proverbs 10:4–6", [["PRO",10,4,6]]],
    ["Proverbs 10:7–9", [["PRO",10,7,9]]],
    ["Proverbs 10:10–12", [["PRO",10,10,12]]],
    ["Proverbs 10:13–15", [["PRO",10,13,15]]],
    ["Proverbs 10:16–18", [["PRO",10,16,18]]],
    ["Proverbs 10:19–20", [["PRO",10,19,20]]],
    ["Proverbs 10:21–22", [["PRO",10,21,22]]],
    ["Proverbs 10:23–24", [["PRO",10,23,24]]],
    ["Proverbs 10:25–26", [["PRO",10,25,26]]],
    ["Proverbs 10:27–28", [["PRO",10,27,28]]],
    ["Proverbs 10:29–30", [["PRO",10,29,30]]],
    ["Proverbs 10:31–32", [["PRO",10,31,32]]],
    ["Proverbs 11:1–3", [["PRO",11,1,3]]],
    ["Proverbs 11:4–6", [["PRO",11,4,6]]],
    ["Proverbs 11:7–9", [["PRO",11,7,9]]],
    ["Proverbs 11:10–12", [["PRO",11,10,12]]],
    ["Proverbs 11:13–15", [["PRO",11,13,15]]],
    ["Proverbs 11:16–18", [["PRO",11,16,18]]],
    ["Proverbs 11:19–21", [["PRO",11,19,21]]],
    ["Proverbs 11:22–23", [["PRO",11,22,23]]],
    ["Proverbs 11:24–25", [["PRO",11,24,25]]],
    ["Proverbs 11:26–27", [["PRO",11,26,27]]],
    ["Proverbs 11:28–29", [["PRO",11,28,29]]],
    ["Proverbs 11:30–31", [["PRO",11,30,31]]],
    ["Proverbs 12:1–3", [["PRO",12,1,3]]],
    ["Proverbs 12:4–6", [["PRO",12,4,6]]],
    ["Proverbs 12:7–9", [["PRO",12,7,9]]],
    ["Proverbs 12:10–12", [["PRO",12,10,12]]],
    ["Proverbs 12:13–15", [["PRO",12,13,15]]],
    ["Proverbs 12:16–18", [["PRO",12,16,18]]],
    ["Proverbs 12:19–20", [["PRO",12,19,20]]],
    ["Proverbs 12:21–22", [["PRO",12,21,22]]],
    ["Proverbs 12:23–24", [["PRO",12,23,24]]],
    ["Proverbs 12:25–26", [["PRO",12,25,26]]],
    ["Proverbs 12:27–28", [["PRO",12,27,28]]],
    ["Proverbs 13:1–3", [["PRO",13,1,3]]],
    ["Proverbs 13:4–6", [["PRO",13,4,6]]],
    ["Proverbs 13:7–9", [["PRO",13,7,9]]],
    ["Proverbs 13:10–12", [["PRO",13,10,12]]],
    ["Proverbs 13:13–15", [["PRO",13,13,15]]],
    ["Proverbs 13:16–17", [["PRO",13,16,17]]],
    ["Proverbs 13:18–19", [["PRO",13,18,19]]],
    ["Proverbs 13:20–21", [["PRO",13,20,21]]],
    ["Proverbs 13:22–23", [["PRO",13,22,23]]],
    ["Proverbs 13:24–25", [["PRO",13,24,25]]],
    ["Proverbs 14:1–3", [["PRO",14,1,3]]],
    ["Proverbs 14:4–6", [["PRO",14,4,6]]],
    ["Proverbs 14:7–9", [["PRO",14,7,9]]],
    ["Proverbs 14:10–12", [["PRO",14,10,12]]],
    ["Proverbs 14:13–15", [["PRO",14,13,15]]],
    ["Proverbs 14:16–18", [["PRO",14,16,18]]],
    ["Proverbs 14:19–21", [["PRO",14,19,21]]],
    ["Proverbs 14:22–23", [["PRO",14,22,23]]],
    ["Proverbs 14:24–25", [["PRO",14,24,25]]],
    ["Proverbs 14:26–27", [["PRO",14,26,27]]],
    ["Proverbs 14:28–29", [["PRO",14,28,29]]],
    ["Proverbs 14:30–31", [["PRO",14,30,31]]],
    ["Proverbs 14:32–33", [["PRO",14,32,33]]],
    ["Proverbs 14:34–35", [["PRO",14,34,35]]],
    ["Proverbs 15:1–3", [["PRO",15,1,3]]],
    ["Proverbs 15:4–6", [["PRO",15,4,6]]],
    ["Proverbs 15:7–9", [["PRO",15,7,9]]],
    ["Proverbs 15:10–12", [["PRO",15,10,12]]],
    ["Proverbs 15:13–15", [["PRO",15,13,15]]],
    ["Proverbs 15:16–18", [["PRO",15,16,18]]],
    ["Proverbs 15:19–21", [["PRO",15,19,21]]],
    ["Proverbs 15:22–23", [["PRO",15,22,23]]],
    ["Proverbs 15:24–25", [["PRO",15,24,25]]],
    ["Proverbs 15:26–27", [["PRO",15,26,27]]],
    ["Proverbs 15:28–29", [["PRO",15,28,29]]],
    ["Proverbs 15:30–31", [["PRO",15,30,31]]],
    ["Proverbs 15:32–33", [["PRO",15,32,33]]],
    ["Proverbs 16:1–3", [["PRO",16,1,3]]],
    ["Proverbs 16:4–6", [["PRO",16,4,6]]],
    ["Proverbs 16:7–9", [["PRO",16,7,9]]],
    ["Proverbs 16:10–12", [["PRO",16,10,12]]],
    ["Proverbs 16:13–15", [["PRO",16,13,15]]],
    ["Proverbs 16:16–18", [["PRO",16,16,18]]],
    ["Proverbs 16:19–21", [["PRO",16,19,21]]],
    ["Proverbs 16:22–23", [["PRO",16,22,23]]],
    ["Proverbs 16:24–25", [["PRO",16,24,25]]],
    ["Proverbs 16:26–27", [["PRO",16,26,27]]],
    ["Proverbs 16:28–29", [["PRO",16,28,29]]],
    ["Proverbs 16:30–31", [["PRO",16,30,31]]],
    ["Proverbs 16:32–33", [["PRO",16,32,33]]],
    ["Proverbs 17:1–3", [["PRO",17,1,3]]],
    ["Proverbs 17:4–6", [["PRO",17,4,6]]],
    ["Proverbs 17:7–9", [["PRO",17,7,9]]],
    ["Proverbs 17:10–12", [["PRO",17,10,12]]],
    ["Proverbs 17:13–15", [["PRO",17,13,15]]],
    ["Proverbs 17:16–18", [["PRO",17,16,18]]],
    ["Proverbs 17:19–20", [["PRO",17,19,20]]],
    ["Proverbs 17:21–22", [["PRO",17,21,22]]],
    ["Proverbs 17:23–24", [["PRO",17,23,24]]],
    ["Proverbs 17:25–26", [["PRO",17,25,26]]],
    ["Proverbs 17:27–28", [["PRO",17,27,28]]],
    ["Proverbs 18:1–3", [["PRO",18,1,3]]],
    ["Proverbs 18:4–6", [["PRO",18,4,6]]],
    ["Proverbs 18:7–9", [["PRO",18,7,9]]],
    ["Proverbs 18:10–12", [["PRO",18,10,12]]],
    ["Proverbs 18:13–14", [["PRO",18,13,14]]],
    ["Proverbs 18:15–16", [["PRO",18,15,16]]],
    ["Proverbs 18:17–18", [["PRO",18,17,18]]],
    ["Proverbs 18:19–20", [["PRO",18,19,20]]],
    ["Proverbs 18:21–22", [["PRO",18,21,22]]],
    ["Proverbs 18:23–24", [["PRO",18,23,24]]],
    ["Proverbs 19:1–3", [["PRO",19,1,3]]],
    ["Proverbs 19:4–6", [["PRO",19,4,6]]],
    ["Proverbs 19:7–9", [["PRO",19,7,9]]],
    ["Proverbs 19:10–12", [["PRO",19,10,12]]],
    ["Proverbs 19:13–15", [["PRO",19,13,15]]],
    ["Proverbs 19:16–17", [["PRO",19,16,17]]],
    ["Proverbs 19:18–19", [["PRO",19,18,19]]],
    ["Proverbs 19:20–21", [["PRO",19,20,21]]],
    ["Proverbs 19:22–23", [["PRO",19,22,23]]],
    ["Proverbs 19:24–25", [["PRO",19,24,25]]],
    ["Proverbs 19:26–27", [["PRO",19,26,27]]],
    ["Proverbs 19:28–29", [["PRO",19,28,29]]],
    ["Proverbs 20:1–3", [["PRO",20,1,3]]],
    ["Proverbs 20:4–6", [["PRO",20,4,6]]],
    ["Proverbs 20:7–9", [["PRO",20,7,9]]],
    ["Proverbs 20:10–12", [["PRO",20,10,12]]],
    ["Proverbs 20:13–15", [["PRO",20,13,15]]],
    ["Proverbs 20:16–18", [["PRO",20,16,18]]],
    ["Proverbs 20:19–20", [["PRO",20,19,20]]],
    ["Proverbs 20:21–22", [["PRO",20,21,22]]],
    ["Proverbs 20:23–24", [["PRO",20,23,24]]],
    ["Proverbs 20:25–26", [["PRO",20,25,26]]],
    ["Proverbs 20:27–28", [["PRO",20,27,28]]],
    ["Proverbs 20:29–30", [["PRO",20,29,30]]],
    ["Proverbs 21:1–3", [["PRO",21,1,3]]],
    ["Proverbs 21:4–6", [["PRO",21,4,6]]],
    ["Proverbs 21:7–9", [["PRO",21,7,9]]],
    ["Proverbs 21:10–12", [["PRO",21,10,12]]],
    ["Proverbs 21:13–15", [["PRO",21,13,15]]],
    ["Proverbs 21:16–18", [["PRO",21,16,18]]],
    ["Proverbs 21:19–21", [["PRO",21,19,21]]],
    ["Proverbs 21:22–23", [["PRO",21,22,23]]],
    ["Proverbs 21:24–25", [["PRO",21,24,25]]],
    ["Proverbs 21:26–27", [["PRO",21,26,27]]],
    ["Proverbs 21:28–29", [["PRO",21,28,29]]],
    ["Proverbs 21:30–31", [["PRO",21,30,31]]],
    ["Proverbs 22:1–3", [["PRO",22,1,3]]],
    ["Proverbs 22:4–6", [["PRO",22,4,6]]],
    ["Proverbs 22:7–9", [["PRO",22,7,9]]],
    ["Proverbs 22:10–12", [["PRO",22,10,12]]],
    ["Proverbs 22:13–15", [["PRO",22,13,15]]],
    ["Proverbs 22:16–17", [["PRO",22,16,17]]],
    ["Proverbs 22:18–19", [["PRO",22,18,19]]],
    ["Proverbs 22:20–21", [["PRO",22,20,21]]],
    ["Proverbs 22:22–23", [["PRO",22,22,23]]],
    ["Proverbs 22:24–25", [["PRO",22,24,25]]],
    ["Proverbs 22:26–27", [["PRO",22,26,27]]],
    ["Proverbs 22:28–29", [["PRO",22,28,29]]],
    ["Proverbs 23:1–3", [["PRO",23,1,3]]],
    ["Proverbs 23:4–6", [["PRO",23,4,6]]],
    ["Proverbs 23:7–9", [["PRO",23,7,9]]],
    ["Proverbs 23:10–12", [["PRO",23,10,12]]],
    ["Proverbs 23:13–15", [["PRO",23,13,15]]],
    ["Proverbs 23:16–18", [["PRO",23,16,18]]],
    ["Proverbs 23:19–21", [["PRO",23,19,21]]],
    ["Proverbs 23:22–23", [["PRO",23,22,23]]],
    ["Proverbs 23:24–25", [["PRO",23,24,25]]],
    ["Proverbs 23:26–27", [["PRO",23,26,27]]],
    ["Proverbs 23:28–29", [["PRO",23,28,29]]],
    ["Proverbs 23:30–31", [["PRO",23,30,31]]],
    ["Proverbs 23:32–33", [["PRO",23,32,33]]],
    ["Proverbs 23:34–35", [["PRO",23,34,35]]],
    ["Proverbs 24:1–3", [["PRO",24,1,3]]],
    ["Proverbs 24:4–6", [["PRO",24,4,6]]],
    ["Proverbs 24:7–9", [["PRO",24,7,9]]],
    ["Proverbs 24:10–12", [["PRO",24,10,12]]],
    ["Proverbs 24:13–15", [["PRO",24,13,15]]],
    ["Proverbs 24:16–18", [["PRO",24,16,18]]],
    ["Proverbs 24:19–20", [["PRO",24,19,20]]],
    ["Proverbs 24:21–22", [["PRO",24,21,22]]],
    ["Proverbs 24:23–24", [["PRO",24,23,24]]],
    ["Proverbs 24:25–26", [["PRO",24,25,26]]],
    ["Proverbs 24:27–28", [["PRO",24,27,28]]],
    ["Proverbs 24:29–30", [["PRO",24,29,30]]],
    ["Proverbs 24:31–32", [["PRO",24,31,32]]],
    ["Proverbs 24:33–34", [["PRO",24,33,34]]],
    ["Proverbs 25:1–3", [["PRO",25,1,3]]],
    ["Proverbs 25:4–6", [["PRO",25,4,6]]],
    ["Proverbs 25:7–9", [["PRO",25,7,9]]],
    ["Proverbs 25:10–12", [["PRO",25,10,12]]],
    ["Proverbs 25:13–15", [["PRO",25,13,15]]],
    ["Proverbs 25:16–18", [["PRO",25,16,18]]],
    ["Proverbs 25:19–20", [["PRO",25,19,20]]],
    ["Proverbs 25:21–22", [["PRO",25,21,22]]],
    ["Proverbs 25:23–24", [["PRO",25,23,24]]],
    ["Proverbs 25:25–26", [["PRO",25,25,26]]],
    ["Proverbs 25:27–28", [["PRO",25,27,28]]],
    ["Proverbs 26:1–3", [["PRO",26,1,3]]],
    ["Proverbs 26:4–6", [["PRO",26,4,6]]],
    ["Proverbs 26:7–9", [["PRO",26,7,9]]],
    ["Proverbs 26:10–12", [["PRO",26,10,12]]],
    ["Proverbs 26:13–15", [["PRO",26,13,15]]],
    ["Proverbs 26:16–18", [["PRO",26,16,18]]],
    ["Proverbs 26:19–20", [["PRO",26,19,20]]],
    ["Proverbs 26:21–22", [["PRO",26,21,22]]],
    ["Proverbs 26:23–24", [["PRO",26,23,24]]],
    ["Proverbs 26:25–26", [["PRO",26,25,26]]],
    ["Proverbs 26:27–28", [["PRO",26,27,28]]],
    ["Proverbs 27:1–3", [["PRO",27,1,3]]],
    ["Proverbs 27:4–6", [["PRO",27,4,6]]],
    ["Proverbs 27:7–9", [["PRO",27,7,9]]],
    ["Proverbs 27:10–12", [["PRO",27,10,12]]],
    ["Proverbs 27:13–15", [["PRO",27,13,15]]],
    ["Proverbs 27:16–17", [["PRO",27,16,17]]],
    ["Proverbs 27:18–19", [["PRO",27,18,19]]],
    ["Proverbs 27:20–21", [["PRO",27,20,21]]],
    ["Proverbs 27:22–23", [["PRO",27,22,23]]],
    ["Proverbs 27:24–25", [["PRO",27,24,25]]],
    ["Proverbs 27:26–27", [["PRO",27,26,27]]],
    ["Proverbs 28:1–3", [["PRO",28,1,3]]],
    ["Proverbs 28:4–6", [["PRO",28,4,6]]],
    ["Proverbs 28:7–9", [["PRO",28,7,9]]],
    ["Proverbs 28:10–12", [["PRO",28,10,12]]],
    ["Proverbs 28:13–15", [["PRO",28,13,15]]],
    ["Proverbs 28:16–18", [["PRO",28,16,18]]],
    ["Proverbs 28:19–20", [["PRO",28,19,20]]],
    ["Proverbs 28:21–22", [["PRO",28,21,22]]],
    ["Proverbs 28:23–24", [["PRO",28,23,24]]],
    ["Proverbs 28:25–26", [["PRO",28,25,26]]],
    ["Proverbs 28:27–28", [["PRO",28,27,28]]],
    ["Proverbs 29:1–3", [["PRO",29,1,3]]],
    ["Proverbs 29:4–6", [["PRO",29,4,6]]],
    ["Proverbs 29:7–9", [["PRO",29,7,9]]],
    ["Proverbs 29:10–12", [["PRO",29,10,12]]],
    ["Proverbs 29:13–15", [["PRO",29,13,15]]],
    ["Proverbs 29:16–17", [["PRO",29,16,17]]],
    ["Proverbs 29:18–19", [["PRO",29,18,19]]],
    ["Proverbs 29:20–21", [["PRO",29,20,21]]],
    ["Proverbs 29:22–23", [["PRO",29,22,23]]],
    ["Proverbs 29:24–25", [["PRO",29,24,25]]],
    ["Proverbs 29:26–27", [["PRO",29,26,27]]],
    ["Proverbs 30:1–3", [["PRO",30,1,3]]],
    ["Proverbs 30:4–6", [["PRO",30,4,6]]],
    ["Proverbs 30:7–9", [["PRO",30,7,9]]],
    ["Proverbs 30:10–12", [["PRO",30,10,12]]],
    ["Proverbs 30:13–15", [["PRO",30,13,15]]],
    ["Proverbs 30:16–18", [["PRO",30,16,18]]],
    ["Proverbs 30:19–21", [["PRO",30,19,21]]],
    ["Proverbs 30:22–23", [["PRO",30,22,23]]],
    ["Proverbs 30:24–25", [["PRO",30,24,25]]],
    ["Proverbs 30:26–27", [["PRO",30,26,27]]],
    ["Proverbs 30:28–29", [["PRO",30,28,29]]],
    ["Proverbs 30:30–31", [["PRO",30,30,31]]],
    ["Proverbs 30:32–33", [["PRO",30,32,33]]],
    ["Proverbs 31:1–3", [["PRO",31,1,3]]],
    ["Proverbs 31:4–6", [["PRO",31,4,6]]],
    ["Proverbs 31:7–9", [["PRO",31,7,9]]],
    ["Proverbs 31:10–12", [["PRO",31,10,12]]],
    ["Proverbs 31:13–15", [["PRO",31,13,15]]],
    ["Proverbs 31:16–18", [["PRO",31,16,18]]],
    ["Proverbs 31:19–21", [["PRO",31,19,21]]],
    ["Proverbs 31:22–23", [["PRO",31,22,23]]],
    ["Proverbs 31:24–25", [["PRO",31,24,25]]],
    ["Proverbs 31:26–27", [["PRO",31,26,27]]],
    ["Proverbs 31:28–29", [["PRO",31,28,29]]],
    ["Proverbs 31:30–31", [["PRO",31,30,31]]],
];

// Today's three readings, each { label, segments:[{bookIdx,chapter,vFrom,vTo}] }.
// Day 366 (leap years) clamps to day 365; the Psalter cycles through its
// 153-entry list (Psalm 119 is spread over 4 days).
function getDailyReadings(date) {
    const bookIdMap = {};
    BIBLE_BOOKS.forEach(([,id], i) => { bookIdMap[id] = i; });
    const dayOfYear = Math.min(365, dayOfYearOf(date));
    const conv = ([label, segs]) => ({
        label,
        segments: segs.map(([id, chapter, vFrom, vTo]) => ({ bookIdx: bookIdMap[id], chapter, vFrom, vTo })),
    });
    return {
        nt:    conv(DAILY_NT_PLAN[dayOfYear - 1]),
        psalm: conv(DAILY_PSALM_PLAN[(dayOfYear - 1) % DAILY_PSALM_PLAN.length]),
        prov:  conv(DAILY_PROV_PLAN[dayOfYear - 1]),
    };
}

function initDaily() {
    const panel = document.getElementById('tab-daily');
    panel.innerHTML = `
    <div class="daily-pane">
      <div class="section-title">Daily Bible</div>
      <div class="sermon-toolbar">
        <button class="sermon-btn" id="daily-prev">◀ Prev</button>
        <span class="section-title flex-1" style="text-align:center" id="daily-date-lbl"></span>
        <button class="sermon-btn" id="daily-next">Next ▶</button>
        <button class="sermon-btn" id="daily-today">Today</button>
      </div>
      <div class="sermon-toolbar">
        <select class="bible-select flex-1" id="daily-trans-sel"></select>
      </div>
      <div class="daily-reading-scroll">
        <div id="daily-reading"></div>
      </div>
    </div>`;

    const transSel = document.getElementById('daily-trans-sel');
    BIBLE_TRANSLATIONS.forEach(([name, code]) => transSel.appendChild(el('option', { value: code }, name)));
    transSel.value = bibleState.translation;
    // Translation is shared with the Bible tab
    transSel.onchange = () => { bibleState.translation = transSel.value; applyBibleState(); dailyRefresh(); };

    document.getElementById('daily-prev').onclick  = () => dailyNav(-1);
    document.getElementById('daily-next').onclick  = () => dailyNav(+1);
    document.getElementById('daily-today').onclick = () => { dailyDate = new Date(); dailyDate.setHours(0,0,0,0); dailyRefresh(); };

    dailyRefresh();
}

function dailyNav(delta) {
    dailyDate = new Date(dailyDate.getTime() + delta * 86400000);
    dailyRefresh();
}

function dailyRefresh() {
    document.getElementById('daily-date-lbl').textContent = formatDateFull(dailyDate);
    const sel = document.getElementById('daily-trans-sel');
    if (sel && sel.value !== bibleState.translation) sel.value = bibleState.translation;
    loadDaily();
}

async function fetchDailyChapter(r) {
    const book = BIBLE_BOOKS[r.bookIdx];
    const key  = `${bibleState.translation}|${book[1]}|${r.chapter}`;
    if (!dailyChapterCache[key]) {
        const params = new URLSearchParams({ book_id: book[1], chapter: r.chapter, translation: bibleState.translation });
        const data = await api('bible.php?' + params);
        if (data.error) return data; // don't cache errors (e.g. missing API key)
        dailyChapterCache[key] = data;
    }
    return dailyChapterCache[key];
}

async function loadDaily() {
    const container = document.getElementById('daily-reading');
    if (!container) return;
    const requestedDate = dailyDate;
    const requestedTrans = bibleState.translation;
    const readings = getDailyReadings(requestedDate);
    const order = [['New Testament', readings.nt], ['Psalm', readings.psalm], ['Proverbs', readings.prov]];

    container.innerHTML = '';
    const bodies = [];
    for (const [label, r] of order) {
        const first = r.segments[0];
        const heading = el('button', { class: 'daily-heading-btn', title: 'Open in Bible tab',
            onclick: () => openBibleRef(first.bookIdx, first.chapter) }, r.label);
        const body = el('div', { class: 'daily-body' }, el('span', { class: 'status-label' }, 'Loading…'));
        container.appendChild(el('div', { class: 'daily-section' },
            el('span', { class: 'section-heading' }, label), heading, body));
        bodies.push(body);
    }

    await Promise.all(order.map(async ([, r], i) => {
        const body = bodies[i];
        try {
            const results = await Promise.all(r.segments.map(seg => fetchDailyChapter(seg)));
            if (requestedDate !== dailyDate || requestedTrans !== bibleState.translation) return; // user navigated away
            body.innerHTML = '';
            const verses = [];
            let citation = '';
            for (let k = 0; k < results.length; k++) {
                const data = results[k], seg = r.segments[k];
                if (data.error) { body.textContent = data.error; return; }
                if (data.raw_paragraphs) {
                    // API.Bible fallback with no verse markers — show the whole chapter
                    if (seg.vFrom != null) body.appendChild(el('div', { class: 'status-label' }, 'Verse ranges unavailable in this translation; showing the whole chapter.'));
                    for (const p of data.raw_paragraphs) body.appendChild(el('p', { class: 'bible-paragraph' }, p));
                    continue;
                }
                let vs = data.verses || [];
                if (seg.vFrom != null) vs = vs.filter(v => v.verse >= seg.vFrom && v.verse <= seg.vTo);
                // Prefix chapter number when a reading spans chapters (e.g. "14:1")
                if (r.segments.length > 1) vs = vs.map(v => ({ verse: `${seg.chapter}:${v.verse}`, text: v.text }));
                verses.push(...vs);
                citation = data.citation || citation;
            }
            if (verses.length) renderVerses(body, verses, citation);
        } catch(e) {
            if (requestedDate !== dailyDate) return;
            body.textContent = 'Could not load reading: ' + e.message;
        }
    }));
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

    renderVerses(textDiv, data.verses || [], data.citation);
}

// Render a verse list into `container`, grouped into paragraphs of 5 verses.
function renderVerses(container, verses, citation) {
    if (!verses.length) { container.textContent = 'No text available.'; return; }
    for (let i = 0; i < verses.length; i += 5) {
        const p = el('p', { class: 'bible-paragraph' });
        for (let j = i; j < Math.min(i+5, verses.length); j++) {
            const v = verses[j];
            p.appendChild(el('sup', { class: 'verse-num' }, String(v.verse)));
            p.appendChild(document.createTextNode(v.text + ' '));
        }
        container.appendChild(p);
    }
    if (citation) {
        container.appendChild(el('span', { class: 'bible-citation' }, citation));
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

    const dayOfYear = dayOfYearOf(date);

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
const PRAYER_DAY_KEYS = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];
const PRAYER_DAY_LABELS = { sun: 'Sunday', mon: 'Monday', tue: 'Tuesday', wed: 'Wednesday', thu: 'Thursday', fri: 'Friday', sat: 'Saturday' };
let weeklyPrayerData = {};
let prayerWeeklyShowAll = false;
let draggedWeeklyPrayer = null; // { day, item }

function prayerTodayKey() {
    return PRAYER_DAY_KEYS[new Date().getDay()];
}

function initPrayer() {
    const panel = document.getElementById('tab-prayer');
    panel.innerHTML = `
    <div class="tab-content">
      <div class="prayer-toolbar">
        <button class="sermon-btn" id="prayer-reset-btn">Reset prayers</button>
      </div>
      <div id="prayer-extras"></div>
      <div class="prayer-add-row">
        <input type="text" class="prayer-input" id="prayer-new-input" placeholder="Add a prayer item…">
        <button class="sermon-btn" id="prayer-add-btn">Add</button>
      </div>
      <div class="prayer-list" id="prayer-list"></div>

      <div class="prayer-weekly-toolbar">
        <div class="prayer-weekly-header" id="prayer-weekly-header"></div>
        <button class="sermon-btn" id="prayer-weekly-toggle-btn">Show full week</button>
      </div>
      <div class="prayer-add-row">
        <input type="text" class="prayer-input" id="prayer-weekly-new-input" placeholder="Add to weekly rotation…">
        <button class="sermon-btn" id="prayer-weekly-add-btn">Add</button>
      </div>
      <div class="prayer-list" id="prayer-weekly-list"></div>
    </div>`;

    document.getElementById('prayer-add-btn').onclick = addPrayer;
    document.getElementById('prayer-new-input').addEventListener('keydown', e => { if (e.key==='Enter') addPrayer(); });
    document.getElementById('prayer-reset-btn').onclick = resetPrayers;
    document.getElementById('prayer-weekly-add-btn').onclick = addWeeklyPrayer;
    document.getElementById('prayer-weekly-new-input').addEventListener('keydown', e => { if (e.key==='Enter') addWeeklyPrayer(); });
    document.getElementById('prayer-weekly-toggle-btn').onclick = () => {
        prayerWeeklyShowAll = !prayerWeeklyShowAll;
        renderWeeklyPrayer();
    };

    loadPrayer();
}

async function loadPrayer() {
    try {
        const data = await api('prayers.php');
        prayerData = data.prayers || [];
        weeklyPrayerData = {};
        PRAYER_DAY_KEYS.forEach(k => { weeklyPrayerData[k] = (data.weekly_prayers && data.weekly_prayers[k]) || []; });
        renderPrayerExtras(data.extras || {});
        renderPrayer();
        renderWeeklyPrayer();
    } catch(e) {
        document.getElementById('prayer-list').textContent = 'Could not load prayers.';
    }
}

// Monthly extras pushed from the desktop app: the church prayer diary
// (day-of-month → names, plus a monthly theme) and mission prayer calendars
// (one per month, e.g. GBM / OMF Myanmar). Mirrors the desktop banners.
const PRAYER_CAL_ACCENTS = { gbm: '#4a9eff', myanmar: '#66bb6a' };

function renderPrayerExtras(extras) {
    const box = document.getElementById('prayer-extras');
    if (!box) return;
    box.innerHTML = '';
    const today = new Date();
    const monthTag = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
    const monthName = today.toLocaleDateString('en-GB', { month: 'long' });

    const diary = extras.diary;
    if (diary && diary.days) {
        const dayNum = Math.min(today.getDate(), 30);
        const names = diary.days[String(dayNum)] || '';
        const theme = (diary.monthly_themes || {})[monthName] || '';
        if (names || theme) {
            const banner = el('div', { class: 'prayer-banner prayer-banner-diary' });
            if (names) banner.appendChild(el('div', { class: 'prayer-banner-main' }, `Day ${dayNum}: ${names}`));
            if (theme) banner.appendChild(el('div', { class: 'prayer-banner-theme' }, `${monthName}: ${theme}`));
            box.appendChild(banner);
        }
    }

    (extras.calendars || []).forEach(cal => {
        if (cal.month !== monthTag) return;
        const entry = (cal.entries || {})[String(today.getDate())] || '';
        if (!entry) return;
        const accent = PRAYER_CAL_ACCENTS[cal.name] || 'var(--accent)';
        const banner = el('div', { class: 'prayer-banner', style: `--banner-accent:${accent}` },
            el('div', { class: 'prayer-banner-title' }, cal.title || cal.name),
            el('div', { class: 'prayer-banner-main' }, entry));
        box.appendChild(banner);
    });
}

function renderPrayer() {
    const list = document.getElementById('prayer-list');
    if (!list) return;
    list.innerHTML = '';

    const undone = prayerData.filter(p => !p.done);
    const done   = prayerData.filter(p => p.done);

    const ctx = {
        data: prayerData,
        save: savePrayerData,
        render: () => { renderPrayer(); renderWeeklyPrayer(); },
        extraButtons: (item, dataIdx) => {
            const moveBtn = el('button', { class: 'prayer-move-btn', title: 'Move to weekly rotation' }, '↷');
            moveBtn.onclick = () => moveToWeekly(dataIdx);
            return [moveBtn];
        },
    };

    undone.forEach((item, i) => {
        list.appendChild(makePrayerItem(item, prayerData.indexOf(item), undone.length, i, ctx));
    });

    if (done.length) {
        list.appendChild(el('div', { class: 'done-divider' }, `Prayed (${done.length})`));
        done.forEach(item => list.appendChild(makePrayerItem(item, prayerData.indexOf(item), 0, 0, ctx)));
    }
}

function renderWeeklyPrayer() {
    const header = document.getElementById('prayer-weekly-header');
    const list = document.getElementById('prayer-weekly-list');
    const toggleBtn = document.getElementById('prayer-weekly-toggle-btn');
    if (!header || !list) return;

    const todayKey = prayerTodayKey();
    toggleBtn.textContent = prayerWeeklyShowAll ? 'Show today only' : 'Show full week';
    list.innerHTML = '';

    if (prayerWeeklyShowAll) {
        header.textContent = 'Weekly rotation — full week (drag items between days)';
        PRAYER_DAY_KEYS.forEach(day => {
            const dayData = weeklyPrayerData[day] || (weeklyPrayerData[day] = []);
            const label = PRAYER_DAY_LABELS[day] + (day === todayKey ? ' (today)' : '');
            list.appendChild(el('div', { class: 'prayer-day-heading' }, `${label} (${dayData.length})`));

            const dayZone = el('div', { class: 'prayer-day-list' });
            setUpPrayerDropzone(dayZone, day);
            list.appendChild(dayZone);

            if (!dayData.length) {
                dayZone.appendChild(el('div', { class: 'prayer-day-empty' }, 'Nothing yet'));
                return;
            }
            appendPrayerDayItems(dayZone, dayData, day);
        });
    } else {
        header.textContent = `Weekly rotation — ${PRAYER_DAY_LABELS[todayKey]}`;
        const dayData = weeklyPrayerData[todayKey] || (weeklyPrayerData[todayKey] = []);
        appendPrayerDayItems(list, dayData, null);
    }
}

function setUpPrayerDropzone(zone, day) {
    zone.addEventListener('dragover', e => {
        if (!draggedWeeklyPrayer) return;
        e.preventDefault();
        zone.classList.add('drag-over');
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.classList.remove('drag-over');
        if (!draggedWeeklyPrayer) return;
        const { day: fromDay, item } = draggedWeeklyPrayer;
        draggedWeeklyPrayer = null;
        if (fromDay === day) return;
        const fromList = weeklyPrayerData[fromDay];
        const idx = fromList.indexOf(item);
        if (idx === -1) return;
        fromList.splice(idx, 1);
        weeklyPrayerData[day].push(item);
        savePrayerData();
        renderWeeklyPrayer();
    });
}

function appendPrayerDayItems(list, dayData, day) {
    const undone = dayData.filter(p => !p.done);
    const done   = dayData.filter(p => p.done);

    const ctx = {
        data: dayData,
        save: savePrayerData,
        render: renderWeeklyPrayer,
        extraButtons: () => [],
        day,
    };

    undone.forEach((item, i) => {
        list.appendChild(makePrayerItem(item, dayData.indexOf(item), undone.length, i, ctx));
    });

    if (done.length) {
        list.appendChild(el('div', { class: 'done-divider' }, `Prayed (${done.length})`));
        done.forEach(item => list.appendChild(makePrayerItem(item, dayData.indexOf(item), 0, 0, ctx)));
    }
}

function makePrayerItem(item, dataIdx, undoneTotal, undonePos, ctx) {
    const data = ctx.data;
    const cb = el('input', { type: 'checkbox' });
    cb.checked = item.done;
    cb.onchange = () => { data[dataIdx].done = cb.checked; ctx.save(); ctx.render(); };

    const txt = makeEditablePrayerText(item.text, newText => {
        data[dataIdx].text = newText;
        ctx.save();
    }, ctx);
    const row = el('div', { class: 'prayer-item' + (item.done ? ' done' : '') }, cb, txt);

    if (ctx.day && !item.done) {
        row.draggable = true;
        row.classList.add('draggable');
        row.addEventListener('dragstart', () => {
            draggedWeeklyPrayer = { day: ctx.day, item };
            row.classList.add('dragging');
        });
        row.addEventListener('dragend', () => {
            row.classList.remove('dragging');
            draggedWeeklyPrayer = null;
        });
    }

    if (!item.done) {
        const upBtn = el('button', { class: 'prayer-move-btn', title: 'Move up' }, '▲');
        const dnBtn = el('button', { class: 'prayer-move-btn', title: 'Move down' }, '▼');
        upBtn.disabled = undonePos === 0;
        dnBtn.disabled = undonePos === undoneTotal - 1;
        upBtn.onclick = () => swapPrayer(dataIdx, -1, ctx);
        dnBtn.onclick = () => swapPrayer(dataIdx, +1, ctx);

        const addSubBtn = el('button', { class: 'prayer-move-btn', title: 'Add sub-point' }, '＋');
        addSubBtn.onclick = () => {
            addInputRow.classList.toggle('hidden');
            if (!addInputRow.classList.contains('hidden')) subInp.focus();
        };

        const delBtn = el('button', { class: 'prayer-move-btn', title: 'Delete prayer' }, '✕');
        delBtn.onclick = () => {
            data.splice(dataIdx, 1);
            ctx.save();
            ctx.render();
        };
        row.append(upBtn, dnBtn, addSubBtn, ...ctx.extraButtons(item, dataIdx), delBtn);
    }

    // Sub-items
    const children = item.children || [];
    const subList = el('div', { class: 'prayer-sublist' });
    children.forEach((child, ci) => subList.appendChild(makeSubPrayerItem(child, dataIdx, ci, ctx)));

    // Inline add-sub-point input
    const subInp = el('input', { type: 'text', class: 'prayer-sub-input', placeholder: 'Add sub-point…' });
    const confirmBtn = el('button', { class: 'sermon-btn' }, 'Add');
    const addInputRow = el('div', { class: 'prayer-sub-add-row hidden' }, subInp, confirmBtn);

    const doAdd = () => {
        const t = subInp.value.trim();
        if (!t) return;
        if (!data[dataIdx].children) data[dataIdx].children = [];
        data[dataIdx].children.push({ text: t, done: false });
        subInp.value = '';
        addInputRow.classList.add('hidden');
        ctx.save();
        ctx.render();
    };
    confirmBtn.onclick = doAdd;
    subInp.addEventListener('keydown', e => {
        if (e.key === 'Enter') doAdd();
        if (e.key === 'Escape') addInputRow.classList.add('hidden');
    });

    return el('div', { class: 'prayer-item-wrapper' }, row, subList, addInputRow);
}

function makeSubPrayerItem(child, parentIdx, childIdx, ctx) {
    const data = ctx.data;
    const cb = el('input', { type: 'checkbox' });
    cb.checked = child.done;
    cb.onchange = () => {
        data[parentIdx].children[childIdx].done = cb.checked;
        ctx.save();
        ctx.render();
    };

    const txt = makeEditablePrayerText(child.text, newText => {
        data[parentIdx].children[childIdx].text = newText;
        ctx.save();
    }, ctx);

    const delBtn = el('button', { class: 'prayer-move-btn', title: 'Remove sub-point' }, '✕');
    delBtn.onclick = () => {
        data[parentIdx].children.splice(childIdx, 1);
        ctx.save();
        ctx.render();
    };

    return el('div', { class: 'prayer-subitem' + (child.done ? ' done' : '') }, cb, txt, delBtn);
}

function makeEditablePrayerText(text, onSave, ctx) {
    const txt = el('span', { class: 'prayer-text', title: 'Click to edit' }, text);
    txt.onclick = () => {
        const inp = el('input', { type: 'text', class: 'prayer-edit-input', value: text });
        txt.replaceWith(inp);
        inp.focus();
        inp.select();

        let cancelled = false;
        const finish = save => {
            const newText = inp.value.trim();
            if (save && !cancelled && newText && newText !== text) {
                onSave(newText);
                ctx.render();
            } else {
                inp.replaceWith(txt);
            }
        };

        inp.addEventListener('blur', () => finish(true));
        inp.addEventListener('keydown', e => {
            if (e.key === 'Enter') { e.preventDefault(); inp.blur(); }
            if (e.key === 'Escape') { cancelled = true; inp.blur(); }
        });
    };
    return txt;
}

function swapPrayer(idx, delta, ctx) {
    const data = ctx.data;
    const target = idx + delta;
    if (target < 0 || target >= data.length) return;
    [data[idx], data[target]] = [data[target], data[idx]];
    ctx.save();
    ctx.render();
}

function addPrayer() {
    const inp = document.getElementById('prayer-new-input');
    const text = inp.value.trim();
    if (!text) return;
    prayerData.push({ text, done: false });
    inp.value = '';
    savePrayerData();
    renderPrayer();
}

function leastPopulatedDay() {
    let best = PRAYER_DAY_KEYS[0];
    PRAYER_DAY_KEYS.forEach(k => {
        if ((weeklyPrayerData[k] || []).length < (weeklyPrayerData[best] || []).length) best = k;
    });
    return best;
}

function addWeeklyPrayer() {
    const inp = document.getElementById('prayer-weekly-new-input');
    const text = inp.value.trim();
    if (!text) return;
    const day = leastPopulatedDay();
    weeklyPrayerData[day].push({ text, done: false });
    inp.value = '';
    savePrayerData();
    renderWeeklyPrayer();
}

function moveToWeekly(dataIdx) {
    const item = prayerData[dataIdx];
    const day = leastPopulatedDay();
    weeklyPrayerData[day].push({ text: item.text, done: false, children: item.children || [] });
    prayerData.splice(dataIdx, 1);
    savePrayerData();
    renderPrayer();
    renderWeeklyPrayer();
}

function resetPrayers() {
    prayerData = prayerData.map(p => ({ ...p, done: false, children: (p.children || []).map(c => ({ ...c, done: false })) }));
    PRAYER_DAY_KEYS.forEach(k => {
        weeklyPrayerData[k] = (weeklyPrayerData[k] || []).map(p => ({ ...p, done: false, children: (p.children || []).map(c => ({ ...c, done: false })) }));
    });
    savePrayerData();
    renderPrayer();
    renderWeeklyPrayer();
}

async function savePrayerData() {
    try {
        await api('prayers.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prayers: prayerData, weekly_prayers: weeklyPrayerData }),
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

    // My email (all users) — used for self-service password reset
    body.appendChild(el('div', { class: 'settings-section-label' }, 'MY EMAIL'));
    const emailRow = el('div', { class: 'settings-row' });
    emailRow.appendChild(el('label', {}, 'Email:'));
    const emailInp = el('input', { type: 'email', class: 'settings-input flex-1', placeholder: 'you@example.com', value: window.INIT_PREFS.user_email || '' });
    emailRow.appendChild(emailInp);
    body.appendChild(emailRow);

    const emailStatus = el('div', { style: 'font-size:12px;min-height:18px' });
    const emailBtn = el('button', { class: 'sermon-btn', style: 'margin-left:0', onclick: async () => {
        const email = emailInp.value.trim();
        try {
            const res = await api('access.php', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'set_email', email }),
            });
            if (res.error) { emailStatus.style.color='#ef5350'; emailStatus.textContent='❌ ' + res.error; }
            else { emailStatus.style.color='#66bb6a'; emailStatus.textContent='✅ Email saved.'; window.INIT_PREFS.user_email = email; }
        } catch(e) { emailStatus.style.color='#ef5350'; emailStatus.textContent='❌ ' + e.message; }
    } }, 'Save email');
    body.appendChild(el('div', { class: 'settings-row' }, emailBtn, emailStatus));
    body.appendChild(el('div', { class: 'status-label', style: 'padding:0' }, 'Used for self-service password reset if you forget your password.'));

    // Change password (all users)
    body.appendChild(el('div', { class: 'settings-section-label' }, 'CHANGE PASSWORD'));
    const pwRow0 = el('div', { class: 'settings-row' });
    pwRow0.appendChild(el('label', {}, 'Current password:'));
    const pwCur = el('input', { type: 'password', class: 'settings-input flex-1', autocomplete: 'current-password' });
    pwRow0.appendChild(pwCur);
    body.appendChild(pwRow0);

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
        const cur = pwCur.value, p1 = pwInp.value, p2 = pwInp2.value;
        if (!p1) return;
        if (!cur) { pwStatus.style.color='#ef5350'; pwStatus.textContent='Enter your current password.'; return; }
        if (p1 !== p2) { pwStatus.style.color='#ef5350'; pwStatus.textContent='Passwords do not match.'; return; }
        if (p1.length < 8) { pwStatus.style.color='#ef5350'; pwStatus.textContent='Must be at least 8 characters.'; return; }
        try {
            const res = await api('access.php', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'change_password', current_password: cur, new_password: p1 }),
            });
            if (res.error) { pwStatus.style.color='#ef5350'; pwStatus.textContent='❌ ' + res.error; }
            else { pwStatus.style.color='#66bb6a'; pwStatus.textContent='✅ Password changed — other devices have been logged out.'; pwCur.value=''; pwInp.value=''; pwInp2.value=''; }
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

        body.appendChild(el('div', { class: 'settings-section-label' }, 'GUEST VISITORS'));
        const visitorsBox = el('div', { id: 'guest-visitors-box' },
            el('span', { class: 'status-label', style: 'padding:0' }, 'Loading…'));
        body.appendChild(visitorsBox);
        loadGuestVisits(visitorsBox);

        body.appendChild(el('div', { class: 'settings-section-label' }, 'LOGIN LOG'));
        const logBox = el('div', { id: 'login-log-box' },
            el('span', { class: 'status-label', style: 'padding:0' }, 'Loading…'));
        body.appendChild(logBox);
        loadLoginLog(logBox);
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

        const listBox = el('div', { style: 'display:none' });
        const toggleBtn = el('button', { class: 'save-btn', style: 'font-size:12px;padding:3px 10px' },
            `Show ${users.length} user${users.length === 1 ? '' : 's'}`);
        toggleBtn.onclick = () => {
            const showing = listBox.style.display !== 'none';
            listBox.style.display = showing ? 'none' : '';
            toggleBtn.textContent = showing ? `Show ${users.length} user${users.length === 1 ? '' : 's'}` : 'Hide users';
        };
        container.appendChild(toggleBtn);
        container.appendChild(listBox);

        users.forEach(u => {
            const username  = typeof u === 'string' ? u : u.username;
            const lastLogin = (typeof u === 'object' && u.last_login)
                ? new Date(u.last_login * 1000).toLocaleString('en-GB', { day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit', hour12:false })
                : null;
            const isAdmin = username === 'paul';
            const wrap = el('div', { style: 'padding:6px 0;border-bottom:1px solid var(--header-border)' });
            const row = el('div', { style: 'display:flex;align-items:center;gap:10px' });
            const resultDiv = el('div', { style: 'margin-top:4px;font-size:12px' });
            const nameLbl = el('span', { style: 'flex:1;font-size:14px' }, username);
            if (isAdmin) nameLbl.appendChild(el('span', { style: 'font-size:11px;color:var(--accent);margin-left:6px' }, '(admin)'));
            if (lastLogin) nameLbl.appendChild(el('span', { style: 'font-size:11px;color:var(--subtext);margin-left:8px' }, 'Last login: ' + lastLogin));
            row.appendChild(nameLbl);

            const emailRow = el('div', { style: 'display:flex;align-items:center;gap:6px;margin-top:4px' });
            const emailInp = el('input', { type: 'email', class: 'settings-input', style: 'flex:1;font-size:12px;padding:3px 8px',
                placeholder: 'No email on file', value: (typeof u === 'object' && u.email) ? u.email : '' });
            const emailStatus = el('span', { style: 'font-size:11px' });
            const emailBtn = el('button', { class: 'save-btn', style: 'font-size:11px;padding:2px 8px',
                onclick: async () => {
                    emailBtn.disabled = true;
                    try {
                        const res = await api('access.php', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ action: 'set_email', username, email: emailInp.value.trim() }),
                        });
                        if (res.error) { emailStatus.style.color = '#ef5350'; emailStatus.textContent = '❌ ' + res.error; }
                        else { emailStatus.style.color = '#66bb6a'; emailStatus.textContent = '✅ Saved'; }
                    } catch(e) {
                        emailStatus.style.color = '#ef5350'; emailStatus.textContent = '❌ ' + e.message;
                    } finally {
                        emailBtn.disabled = false;
                    }
                }
            }, 'Save');
            emailRow.append(el('label', { style: 'font-size:11px;color:var(--subtext)' }, 'Email:'), emailInp, emailBtn, emailStatus);

            const resetBtn = el('button', { class: 'save-btn', style: 'font-size:12px;padding:3px 10px',
                onclick: async () => {
                    if (!confirm(`Reset password for "${username}"? A new random password will be generated.`)) return;
                    resetBtn.disabled = true;
                    try {
                        const res = await api('access.php', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ action: 'reset_password', username }),
                        });
                        if (res.error) {
                            resultDiv.style.color = '#ef5350';
                            resultDiv.textContent = '❌ ' + res.error;
                        } else {
                            resultDiv.style.color = '#66bb6a';
                            resultDiv.innerHTML = `✅ New password for <strong>${res.username}</strong>: <strong>${res.password}</strong> &nbsp; <em>(share this once — it won't show again)</em>`;
                        }
                    } catch(e) {
                        resultDiv.style.color = '#ef5350';
                        resultDiv.textContent = '❌ ' + e.message;
                    } finally {
                        resetBtn.disabled = false;
                    }
                }
            }, 'Reset password');
            row.appendChild(resetBtn);

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
            wrap.append(row, emailRow, resultDiv);
            listBox.appendChild(wrap);
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
            if (r.email) {
                info.appendChild(el('div', { style: 'font-size:12px;color:var(--subtext);margin-top:2px' }, r.email));
            }
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

/* ── GUEST VISITORS (admin only) ───────────────────────────────────── */
async function loadGuestVisits(container) {
    try {
        const data = await api('guest_visits.php');
        container.innerHTML = '';
        container.appendChild(el('div', { style: 'font-size:14px;padding:4px 0' },
            'Total guest page views: ', el('strong', {}, String(data.total || 0))));
    } catch(e) {
        container.textContent = 'Could not load visitor count.';
    }
}

/* ── LOGIN LOG (admin only) ─────────────────────────────────────────── */
async function loadLoginLog(container) {
    try {
        const data = await api('login_log.php');
        const entries = data.entries || [];
        container.innerHTML = '';
        if (!entries.length) {
            container.appendChild(el('div', { class: 'status-label', style: 'padding:0' }, 'No login events recorded yet.'));
            return;
        }
        const shown = entries.slice(0, 50);
        shown.forEach(e => {
            const d   = new Date(e.ts * 1000);
            const ts  = d.toLocaleString('en-GB', { day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit', hour12:false });
            const row = el('div', { style: 'display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid var(--header-border);font-size:13px' });
            row.append(
                el('span', { style: `color:${e.ok ? '#66bb6a' : '#ef5350'};min-width:14px;flex-shrink:0` }, e.ok ? '✓' : '✗'),
                el('span', { style: 'min-width:80px;flex-shrink:0' }, e.user),
                el('span', { style: 'color:var(--subtext);font-size:11px;flex:1' }, e.ip || ''),
                el('span', { style: 'color:var(--subtext);font-size:11px;min-width:52px;text-align:center;flex-shrink:0' }, e.method),
                el('span', { style: 'color:var(--subtext);font-size:11px;white-space:nowrap;flex-shrink:0' }, ts),
            );
            container.appendChild(row);
        });
        if (entries.length > 50) {
            container.appendChild(el('div', { class: 'status-label', style: 'padding:4px 0;font-size:11px' }, `Showing 50 of ${entries.length} events`));
        }
    } catch(e) {
        container.textContent = 'Could not load login log.';
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
