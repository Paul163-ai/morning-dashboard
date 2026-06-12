<?php
header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../helpers.php';
require_once __DIR__ . '/../config.php';

$comments_file = __DIR__ . '/../data/spurgeon_comments.json';

function load_comments(string $file): array {
    if (!file_exists($file)) return [];
    $data = json_decode(file_get_contents($file), true);
    return is_array($data) ? $data : [];
}

function save_comments(string $file, array $data): void {
    file_put_contents($file, json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE), LOCK_EX);
}

$user   = current_user();
$method = $_SERVER['REQUEST_METHOD'];

if ($method === 'GET') {
    $date = preg_replace('/[^0-9\-]/', '', $_GET['date'] ?? date('Y-m-d'));
    $data = load_comments($comments_file);
    echo json_encode(['comments' => array_values($data[$date] ?? [])]);

} elseif ($method === 'POST') {
    $body = json_decode(file_get_contents('php://input'), true);
    $date = preg_replace('/[^0-9\-]/', '', $body['date'] ?? date('Y-m-d'));
    $text = substr(trim($body['text'] ?? ''), 0, 8000);
    if ($text === '') { http_response_code(400); echo json_encode(['error' => 'empty']); exit; }

    $data = load_comments($comments_file);
    if (!isset($data[$date])) $data[$date] = [];
    $comment = [
        'id'        => bin2hex(random_bytes(8)),
        'username'  => $user,
        'text'      => $text,
        'timestamp' => time(),
    ];
    $data[$date][] = $comment;
    save_comments($comments_file, $data);
    echo json_encode(['ok' => true, 'comment' => $comment]);

} elseif ($method === 'DELETE') {
    $body = json_decode(file_get_contents('php://input'), true);
    $date = preg_replace('/[^0-9\-]/', '', $body['date'] ?? '');
    $id   = preg_replace('/[^a-f0-9]/', '', $body['id']   ?? '');

    $data = load_comments($comments_file);
    if (!isset($data[$date])) { echo json_encode(['ok' => true]); exit; }

    $data[$date] = array_values(array_filter($data[$date], function ($c) use ($id, $user) {
        if ($c['id'] !== $id) return true;
        return !($c['username'] === $user || $user === ADMIN_USER);
    }));

    save_comments($comments_file, $data);
    echo json_encode(['ok' => true]);
} else {
    http_response_code(405);
    echo json_encode(['error' => 'method not allowed']);
}
