<?php
header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../helpers.php';

$sermons_dir = user_data_dir() . '/sermons';

function safe_filename(string $title): string {
    $name = preg_replace('/[\/\\\\:*?"<>|]/', '-', $title);
    $name = trim($name, '. ');
    return substr($name, 0, 200) . '.txt';
}

$method = $_SERVER['REQUEST_METHOD'];

if ($method === 'DELETE') {
    $file = basename($_GET['file'] ?? '');
    if (!$file || !str_ends_with($file, '.txt')) {
        http_response_code(400); echo json_encode(['error' => 'Invalid filename']); exit;
    }
    $path = $sermons_dir . '/' . $file;
    if (file_exists($path)) unlink($path);
    echo json_encode(['ok' => true]);

} elseif ($method === 'POST') {
    $body    = json_decode(file_get_contents('php://input'), true);
    $title   = trim($body['title']    ?? '');
    $text    = $body['text']           ?? '';
    $old_file = basename($body['old_file'] ?? '');

    if (!$title) { http_response_code(400); echo json_encode(['error' => 'Title required']); exit; }

    $new_file = safe_filename($title);
    $new_path = $sermons_dir . '/' . $new_file;
    $real_dir = realpath($sermons_dir);
    if (!$real_dir || !str_starts_with(realpath(dirname($new_path)) ?: '', $real_dir)) {
        http_response_code(400); echo json_encode(['error' => 'Invalid path']); exit;
    }
    file_put_contents($new_path, $text, LOCK_EX);

    // Remove old file if renamed
    if ($old_file && $old_file !== $new_file) {
        $old_path = $sermons_dir . '/' . $old_file;
        if (file_exists($old_path)) unlink($old_path);
    }

    echo json_encode(['ok' => true, 'file' => $new_file]);

} elseif (isset($_GET['file'])) {
    $file = basename($_GET['file']);
    if (!$file || !str_ends_with($file, '.txt')) {
        http_response_code(400); echo json_encode(['error' => 'Invalid filename']); exit;
    }
    $path = $sermons_dir . '/' . $file;
    $text = file_exists($path) ? file_get_contents($path) : '';
    echo json_encode(['text' => $text], JSON_UNESCAPED_UNICODE);

} else {
    // List all sermons
    $files = glob($sermons_dir . '/*.txt');
    $names = array_map('basename', $files ?: []);
    sort($names);
    echo json_encode(['sermons' => $names]);
}
