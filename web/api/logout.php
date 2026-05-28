<?php
require_once __DIR__ . '/../helpers.php';

$token = $_COOKIE['remember_me'] ?? '';
if ($token !== '') {
    invalidate_remember_token($token);
    setcookie('remember_me', '', ['expires' => 1, 'path' => '/', 'secure' => true, 'httponly' => true, 'samesite' => 'Lax']);
}

$_SESSION = [];
session_destroy();

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['ok' => true]);
} else {
    header('Location: /login.php');
}
exit;
