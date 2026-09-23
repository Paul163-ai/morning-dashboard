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

// Locked read-modify-write of the shared comments file (see update_json()).
function update_comments(string $file, callable $fn): bool {
    return update_json($file, $fn, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
}

// Spurgeon's Morning & Evening repeats on the same month-day every year, so
// comments are keyed by month-day (not full date) and accumulate across years.
function md_key(string $date): string {
    return substr($date, 5, 5);
}

$user   = current_user();
$method = $_SERVER['REQUEST_METHOD'];

if ($method === 'GET') {
    $key  = md_key(preg_replace('/[^0-9\-]/', '', $_GET['date'] ?? date('Y-m-d')));
    $data = load_comments($comments_file);
    $comments = $data[$key] ?? [];
    usort($comments, fn($a, $b) => $a['timestamp'] <=> $b['timestamp']);
    echo json_encode(['comments' => array_values($comments)]);

} elseif ($method === 'POST') {
    $body = json_decode(file_get_contents('php://input'), true);
    $key  = md_key(preg_replace('/[^0-9\-]/', '', $body['date'] ?? date('Y-m-d')));
    $text = clip_text(trim($body['text'] ?? ''), 8000);
    if ($text === '') { http_response_code(400); echo json_encode(['error' => 'empty']); exit; }

    $comment = [
        'id'        => bin2hex(random_bytes(8)),
        'username'  => $user,
        'text'      => $text,
        'timestamp' => time(),
    ];
    $saved = update_comments($comments_file, function ($data) use ($key, $comment) {
        $data[$key][] = $comment;
        return $data;
    });
    if (!$saved) {
        http_response_code(500);
        echo json_encode(['error' => 'Could not save comment']);
        exit;
    }
    echo json_encode(['ok' => true, 'comment' => $comment]);

} elseif ($method === 'DELETE') {
    $body = json_decode(file_get_contents('php://input'), true);
    $key = md_key(preg_replace('/[^0-9\-]/', '', $body['date'] ?? ''));
    $id  = preg_replace('/[^a-f0-9]/', '', $body['id']   ?? '');

    update_comments($comments_file, function ($data) use ($key, $id, $user) {
        if (!isset($data[$key])) return null;
        $data[$key] = array_values(array_filter($data[$key], function ($c) use ($id, $user) {
            if ($c['id'] !== $id) return true;
            return !($c['username'] === $user || $user === ADMIN_USER);
        }));
        return $data;
    });
    echo json_encode(['ok' => true]);
} else {
    http_response_code(405);
    echo json_encode(['error' => 'method not allowed']);
}
