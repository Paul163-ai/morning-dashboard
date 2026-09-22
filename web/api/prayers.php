<?php
header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../helpers.php';

$file = user_data_dir() . '/prayers.json';
// Monthly extras (church prayer diary + mission calendars) pushed from the
// desktop app. Kept in a separate file so browser-side prayer saves, which
// never send "extras", can't wipe them.
$extrasFile = user_data_dir() . '/prayer_extras.json';
$DAY_KEYS = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];

function clean_text($v, $max) {
    return substr(strip_tags((string)$v), 0, $max);
}

function sanitize_day_map($map, $max) {
    $out = [];
    foreach (is_array($map) ? $map : [] as $k => $v) {
        $day = (int)$k;
        if ($day >= 1 && $day <= 31) $out[(string)$day] = clean_text($v, $max);
    }
    return $out;
}

function sanitize_extras($in) {
    $out = ['diary' => null, 'calendars' => []];
    if (is_array($in['diary'] ?? null)) {
        $themes = [];
        foreach (is_array($in['diary']['monthly_themes'] ?? null) ? $in['diary']['monthly_themes'] : [] as $m => $t) {
            $themes[clean_text($m, 20)] = clean_text($t, 500);
        }
        $out['diary'] = [
            'days'           => sanitize_day_map($in['diary']['days'] ?? [], 500),
            'monthly_themes' => $themes,
        ];
    }
    foreach (is_array($in['calendars'] ?? null) ? $in['calendars'] : [] as $cal) {
        if (!is_array($cal)) continue;
        $month = (string)($cal['month'] ?? '');
        if (!preg_match('/^\d{4}-\d{2}$/', $month)) continue;
        $out['calendars'][] = [
            'name'    => preg_replace('/[^a-z0-9_-]/', '', strtolower((string)($cal['name'] ?? ''))),
            'month'   => $month,
            'title'   => clean_text($cal['title'] ?? '', 200),
            'verse'   => clean_text($cal['verse'] ?? '', 500),
            'entries' => sanitize_day_map($cal['entries'] ?? [], 2000),
        ];
    }
    return $out;
}

function load_extras($extrasFile) {
    if (!file_exists($extrasFile)) return ['diary' => null, 'calendars' => []];
    $d = json_decode(file_get_contents($extrasFile), true);
    return is_array($d) ? $d : ['diary' => null, 'calendars' => []];
}

function sanitize_prayer_list($list) {
    return array_values(array_map(function($p) {
        $children = array_values(array_map(function($c) {
            return [
                'text' => substr(strip_tags($c['text'] ?? ''), 0, 500),
                'done' => (bool)($c['done'] ?? false),
            ];
        }, $p['children'] ?? []));
        return [
            'text'     => substr(strip_tags($p['text'] ?? ''), 0, 500),
            'done'     => (bool)($p['done'] ?? false),
            'children' => $children,
        ];
    }, is_array($list) ? $list : []));
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $body = json_decode(file_get_contents('php://input'), true);
    if (!isset($body['prayers']) || !is_array($body['prayers'])) {
        http_response_code(400);
        echo json_encode(['error' => 'Invalid payload']);
        exit;
    }
    $prayers = sanitize_prayer_list($body['prayers']);

    $weeklyIn = is_array($body['weekly_prayers'] ?? null) ? $body['weekly_prayers'] : [];
    $weekly = [];
    foreach ($DAY_KEYS as $day) {
        $weekly[$day] = sanitize_prayer_list($weeklyIn[$day] ?? []);
    }

    file_put_contents($file, json_encode(
        ['prayers' => $prayers, 'weekly_prayers' => $weekly],
        JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE
    ));
    if (isset($body['extras']) && is_array($body['extras'])) {
        file_put_contents($extrasFile, json_encode(
            sanitize_extras($body['extras']),
            JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE
        ));
    }
    echo json_encode(['ok' => true]);
} else {
    $weekly = array_fill_keys($DAY_KEYS, []);
    if (file_exists($file)) {
        $data = json_decode(file_get_contents($file), true);
        foreach ($DAY_KEYS as $day) {
            $weekly[$day] = $data['weekly_prayers'][$day] ?? [];
        }
        echo json_encode(['prayers' => $data['prayers'] ?? [], 'weekly_prayers' => $weekly,
                          'extras' => load_extras($extrasFile)], JSON_UNESCAPED_UNICODE);
    } else {
        echo json_encode(['prayers' => [], 'weekly_prayers' => $weekly,
                          'extras' => load_extras($extrasFile)], JSON_UNESCAPED_UNICODE);
    }
}
