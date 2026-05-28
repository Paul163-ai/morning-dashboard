<?php
header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../helpers.php';

$file = user_data_dir() . '/prayers.json';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $body = json_decode(file_get_contents('php://input'), true);
    if (!isset($body['prayers']) || !is_array($body['prayers'])) {
        http_response_code(400);
        echo json_encode(['error' => 'Invalid payload']);
        exit;
    }
    $prayers = array_values(array_map(function($p) {
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
    }, $body['prayers']));

    file_put_contents($file, json_encode(['prayers' => $prayers], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
    echo json_encode(['ok' => true]);
} else {
    if (file_exists($file)) {
        $data = json_decode(file_get_contents($file), true);
        echo json_encode(['prayers' => $data['prayers'] ?? []], JSON_UNESCAPED_UNICODE);
    } else {
        echo json_encode(['prayers' => []]);
    }
}
