<?php
header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../helpers.php';
require_once __DIR__ . '/../config.php';

$requests_file = __DIR__ . '/../data/access_requests.json';
$body          = json_decode(file_get_contents('php://input'), true) ?? [];
$action        = $body['action'] ?? $_GET['action'] ?? '';

// change_password is available to any logged-in user
if ($action === 'change_password') {
    $current_user = current_user();
    $new_pass     = $body['new_password'] ?? '';
    if (strlen($new_pass) < 8) {
        http_response_code(400);
        echo json_encode(['error' => 'Password must be at least 8 characters.']);
        exit;
    }
    echo json_encode(write_htpasswd(HTPASSWD_FILE, $current_user, $new_pass)
        ? ['ok' => true]
        : ['error' => 'Could not write to .htpasswd — check the path in config.php']);
    exit;
}

// All other actions are admin-only
if (current_user() !== ADMIN_USER) {
    http_response_code(403);
    echo json_encode(['error' => 'Forbidden']);
    exit;
}

/* ── Helpers ─────────────────────────────────────────────────────── */

function load_requests(string $file): array {
    return file_exists($file) ? (json_decode(file_get_contents($file), true) ?: []) : [];
}

function save_requests(string $file, array $requests): void {
    file_put_contents($file, json_encode(array_values($requests), JSON_PRETTY_PRINT));
}

function read_htpasswd_lines(): array {
    return file_exists(HTPASSWD_FILE)
        ? file(HTPASSWD_FILE, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES)
        : [];
}

/* ── Actions ─────────────────────────────────────────────────────── */

if ($action === 'list') {
    echo json_encode(['requests' => load_requests($requests_file)]);

} elseif ($action === 'list_users') {
    $lines = read_htpasswd_lines();
    $users = array_values(array_filter(array_map(fn($l) => explode(':', $l)[0], $lines)));
    echo json_encode(['users' => $users]);

} elseif ($action === 'approve') {
    $username = preg_replace('/[^a-zA-Z0-9_\-]/', '', $body['username'] ?? '');
    if (!$username) { http_response_code(400); echo json_encode(['error' => 'No username']); exit; }

    // Find the pending request to check for a pre-hashed password
    $requests     = load_requests($requests_file);
    $stored_hash  = null;
    foreach ($requests as $r) {
        if ($r['username'] === $username && $r['status'] === 'pending') {
            $stored_hash = $r['password_hash'] ?? null;
            break;
        }
    }

    $response_password = null;
    if ($stored_hash) {
        // User chose their own password at request time — write the hash directly
        if (!write_htpasswd_prehashed(HTPASSWD_FILE, $username, $stored_hash)) {
            echo json_encode(['error' => 'Could not write to .htpasswd — check the path in config.php']);
            exit;
        }
    } else {
        // Legacy request (no hash stored) — generate a random password for the admin to share
        $response_password = substr(str_replace(['+','/','='], '', base64_encode(random_bytes(16))), 0, 16);
        if (!write_htpasswd(HTPASSWD_FILE, $username, $response_password)) {
            echo json_encode(['error' => 'Could not write to .htpasswd — check the path in config.php']);
            exit;
        }
    }

    foreach ($requests as &$r) {
        if ($r['username'] === $username && $r['status'] === 'pending') {
            $r['status'] = 'approved'; $r['approved'] = date('Y-m-d H:i:s'); break;
        }
    }
    save_requests($requests_file, $requests);
    $result = ['ok' => true, 'username' => $username, 'user_set_password' => (bool)$stored_hash];
    if ($response_password) $result['password'] = $response_password;
    echo json_encode($result);

} elseif ($action === 'deny') {
    $username = preg_replace('/[^a-zA-Z0-9_\-]/', '', $body['username'] ?? '');
    $requests = load_requests($requests_file);
    foreach ($requests as &$r) {
        if ($r['username'] === $username && $r['status'] === 'pending') {
            $r['status'] = 'denied'; break;
        }
    }
    save_requests($requests_file, $requests);
    echo json_encode(['ok' => true]);

} elseif ($action === 'delete_user') {
    $username = preg_replace('/[^a-zA-Z0-9_\-]/', '', $body['username'] ?? '');
    if (!$username || $username === ADMIN_USER) {
        http_response_code(400);
        echo json_encode(['error' => 'Cannot delete that user.']);
        exit;
    }

    // Remove from .htpasswd
    $lines = read_htpasswd_lines();
    $lines = array_values(array_filter($lines, fn($l) => !str_starts_with($l, $username . ':')));
    file_put_contents(HTPASSWD_FILE, implode("\n", $lines) . "\n");

    // Remove user data directory
    $user_dir = __DIR__ . '/../data/users/' . $username;
    if (is_dir($user_dir)) {
        // Recursively delete
        $it = new RecursiveDirectoryIterator($user_dir, FilesystemIterator::SKIP_DOTS);
        $files = new RecursiveIteratorIterator($it, RecursiveIteratorIterator::CHILD_FIRST);
        foreach ($files as $file) {
            $file->isDir() ? rmdir($file->getRealPath()) : unlink($file->getRealPath());
        }
        rmdir($user_dir);
    }

    echo json_encode(['ok' => true]);

} else {
    http_response_code(400);
    echo json_encode(['error' => 'Unknown action']);
}
