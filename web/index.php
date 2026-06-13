<?php
require_once __DIR__ . '/helpers.php';

$guest    = !is_authenticated();
$username = current_user();
$prefs    = [];

if ($guest) {
    $theme             = 'dark';
    $font_size         = 13;
    $all_tabs          = ['spurgeon'];
    $tab_order         = ['spurgeon'];
    $visible_tabs      = ['spurgeon'];
    $sidebar_collapsed = false;
} else {
    $prefs_file = user_data_dir() . '/prefs.json';
    if (file_exists($prefs_file)) {
        $prefs = json_decode(file_get_contents($prefs_file), true) ?: [];
    }
    $theme            = $prefs['theme']            ?? 'dark';
    $font_size        = (int)($prefs['font_size']  ?? 13);
    $all_tabs         = ['spurgeon','prayer','news','bible','weather','notes','sermons'];
    $tab_order        = $prefs['tab_order']        ?? $all_tabs;
    $visible_tabs     = $prefs['visible_tabs']     ?? $all_tabs;
    $sidebar_collapsed = (bool)($prefs['sidebar_collapsed'] ?? false);

    // Ensure all tabs are represented in tab_order
    foreach ($all_tabs as $t) {
        if (!in_array($t, $tab_order)) $tab_order[] = $t;
    }
}

$init_prefs = json_encode([
    'theme'             => $theme,
    'font_size'         => $font_size,
    'tab_order'         => $tab_order,
    'visible_tabs'      => $visible_tabs,
    'sidebar_collapsed' => $sidebar_collapsed,
    'weather_location'  => $prefs['weather_location'] ?? '',
    'weather_lat'       => $prefs['weather_lat']      ?? null,
    'weather_lon'       => $prefs['weather_lon']      ?? null,
    'api_bible_key_set' => !empty($prefs['api_bible_key']),
], JSON_HEX_TAG | JSON_HEX_APOS | JSON_HEX_QUOT | JSON_UNESCAPED_UNICODE);
?>
<!DOCTYPE html>
<html lang="en" data-theme="<?= htmlspecialchars($theme) ?>">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>☀️ Morning Dashboard</title>
    <link rel="icon" type="image/png" href="static/favicon.png">
    <link rel="stylesheet" href="static/style.css">
    <style>
        :root { --font-size: <?= $font_size ?>px; }
    </style>
</head>
<body<?= $guest ? ' class="guest"' : '' ?>>
<div id="app">

    <header id="header">
        <div class="app-title">☀️ Morning Dashboard</div>
        <div class="date-label" id="date-label"></div>
        <?php if ($guest): ?>
        <a class="logout-btn" href="/login.php">Log in</a>
        <?php else: ?>
        <div class="user-label"><?= htmlspecialchars($username) ?></div>
        <button class="prefs-button" id="settings-btn">⚙️ Settings</button>
        <button class="logout-btn" id="logout-btn">Log out</button>
        <?php endif; ?>
    </header>

    <div id="body">
        <nav id="sidebar"<?= $sidebar_collapsed ? ' class="collapsed"' : '' ?>>
            <div id="icon-col">
                <!-- icon rows injected by JS -->
                <div class="sidebar-spacer"></div>
                <button class="sidebar-collapse-btn" id="collapse-btn">
                    <?= $sidebar_collapsed ? '▶' : '◀' ?>
                </button>
            </div>
            <div id="label-col"<?= $sidebar_collapsed ? ' class="hidden"' : '' ?>>
                <!-- label buttons injected by JS -->
                <div class="sidebar-spacer"></div>
            </div>
        </nav>

        <main id="content">
            <?php foreach ($all_tabs as $tab): ?>
            <div id="tab-<?= $tab ?>" class="tab-panel"></div>
            <?php endforeach; ?>
        </main>
    </div>

    <?php if ($guest): ?>
    <footer id="guest-footer">
        <a href="/login.php">Log in for more features</a>
    </footer>
    <?php endif; ?>
</div>

<?php if (!$guest): ?>
<!-- Settings Modal -->
<div id="settings-modal" class="modal-overlay" hidden>
    <div class="modal-box">
        <div class="modal-header">
            <h2>⚙️ Settings</h2>
            <button class="modal-close-btn" id="close-settings-btn">✕</button>
        </div>
        <div class="modal-body" id="settings-body"></div>
        <div class="modal-footer">
            <button class="cancel-btn" id="cancel-settings-btn">Cancel</button>
            <button class="save-btn"   id="save-settings-btn">Save</button>
        </div>
    </div>
</div>
<?php endif; ?>

<script>
window.INIT_PREFS  = <?= $init_prefs ?>;
window.IS_ADMIN      = <?= (!$guest && current_user() === ADMIN_USER) ? 'true' : 'false' ?>;
window.CURRENT_USER  = <?= json_encode(current_user()) ?>;
window.IS_GUEST      = <?= $guest ? 'true' : 'false' ?>;
</script>
<script src="static/app.js"></script>
</body>
</html>
