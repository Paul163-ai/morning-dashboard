<?php
header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../helpers.php';

$file = user_data_dir() . '/notes.txt';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $body = json_decode(file_get_contents('php://input'), true);
    $text = $body['text'] ?? '';
    file_put_contents($file, $text, LOCK_EX);
    echo json_encode(['ok' => true]);
} else {
    $text = file_exists($file) ? file_get_contents($file) : '';
    echo json_encode(['text' => $text], JSON_UNESCAPED_UNICODE);
}
