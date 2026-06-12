<?php
header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../helpers.php';
require_once __DIR__ . '/../config.php';

$cache_file = __DIR__ . '/../data/spurgeon_modern_cache.json';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (current_user() !== ADMIN_USER) {
        http_response_code(403);
        echo json_encode(['error' => 'Forbidden']);
        exit;
    }
    $body = json_decode(file_get_contents('php://input'), true) ?? [];
    $date = $body['date'] ?? '';
    if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $date)) {
        http_response_code(400);
        echo json_encode(['error' => 'Invalid date']);
        exit;
    }
    $cache = file_exists($cache_file) ? (json_decode(file_get_contents($cache_file), true) ?: []) : [];
    $cache[$date] = ['am' => $body['am'] ?? '', 'pm' => $body['pm'] ?? ''];
    file_put_contents($cache_file, json_encode($cache, JSON_UNESCAPED_UNICODE), LOCK_EX);
    echo json_encode(['ok' => true]);
    exit;
}

$date_str = $_GET['date'] ?? date('Y-m-d');
$cache     = file_exists($cache_file) ? (json_decode(file_get_contents($cache_file), true) ?: []) : [];
echo json_encode($cache[$date_str] ?? ['am' => '', 'pm' => ''], JSON_UNESCAPED_UNICODE);
