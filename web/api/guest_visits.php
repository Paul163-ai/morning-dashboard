<?php
header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../helpers.php';
require_once __DIR__ . '/../config.php';

if (current_user() !== ADMIN_USER) {
    http_response_code(403);
    echo json_encode(['error' => 'Forbidden']);
    exit;
}

$file = __DIR__ . '/../data/guest_visits.json';
$data = file_exists($file) ? (json_decode(file_get_contents($file), true) ?: []) : [];
echo json_encode(['total' => $data['total'] ?? 0, 'entries' => $data['entries'] ?? []]);
