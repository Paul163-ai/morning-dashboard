<?php
header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../helpers.php';

$file = user_data_dir() . '/prefs.json';

$ALL_TABS = ['daily','spurgeon','systematics','news','weather','bible','prayer','notes','sermons','resources'];

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $body = json_decode(file_get_contents('php://input'), true);
    if (!is_array($body)) { http_response_code(400); echo json_encode(['error' => 'Invalid']); exit; }

    // Sanitise
    $prefs = [];
    $prefs['theme']             = in_array($body['theme'] ?? 'dark', ['dark','light']) ? $body['theme'] : 'dark';
    $prefs['font_size']         = max(9, min(24, (int)($body['font_size'] ?? 13)));
    $prefs['weather_location']  = clip_text(strip_tags($body['weather_location'] ?? ''), 200);
    $prefs['weather_lat']       = isset($body['weather_lat'])  ? (float)$body['weather_lat']  : null;
    $prefs['weather_lon']       = isset($body['weather_lon'])  ? (float)$body['weather_lon']  : null;
    // Preserve existing key if nothing new was submitted
    $existing = file_exists($file) ? (json_decode(file_get_contents($file), true) ?: []) : []; // $file is already per-user
    $new_key  = trim($body['api_bible_key'] ?? '');
    $prefs['api_bible_key'] = $new_key !== '' ? substr($new_key, 0, 200) : ($existing['api_bible_key'] ?? '');
    $prefs['sidebar_collapsed'] = (bool)($body['sidebar_collapsed'] ?? false);
    $prefs['spurgeon_version']  = in_array($body['spurgeon_version'] ?? 'original', ['original','modern']) ? $body['spurgeon_version'] : 'original';

    $tab_order    = array_filter((array)($body['tab_order']    ?? $ALL_TABS), fn($k) => in_array($k, $ALL_TABS));
    $visible_tabs = array_filter((array)($body['visible_tabs'] ?? $ALL_TABS), fn($k) => in_array($k, $ALL_TABS));
    // Ensure all tabs appear in order
    foreach ($ALL_TABS as $t) {
        if (!in_array($t, $tab_order)) $tab_order[] = $t;
    }
    $prefs['tab_order']    = array_values($tab_order);
    $prefs['visible_tabs'] = array_values($visible_tabs);

    if (!save_json($file, $prefs, JSON_PRETTY_PRINT)) {
        http_response_code(500);
        echo json_encode(['error' => 'Could not save prefs']);
        exit;
    }
    echo json_encode(['ok' => true]);
} else {
    if (file_exists($file)) {
        $prefs = json_decode(file_get_contents($file), true) ?: [];
    } else {
        $prefs = [];
    }
    echo json_encode($prefs, JSON_UNESCAPED_UNICODE);
}
