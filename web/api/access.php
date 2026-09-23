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

// set_email is available to any logged-in user for their own account;
// the admin may also target another user by passing "username".
if ($action === 'set_email') {
    $target = current_user();
    if (current_user() === ADMIN_USER && !empty($body['username'])) {
        $target = preg_replace('/[^a-zA-Z0-9_\-]/', '', $body['username']);
    }
    $email = trim($body['email'] ?? '');
    if ($email !== '' && !filter_var($email, FILTER_VALIDATE_EMAIL)) {
        http_response_code(400);
        echo json_encode(['error' => 'Please enter a valid email address.']);
        exit;
    }
    set_user_email($target, $email);
    echo json_encode(['ok' => true]);
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
    save_json($file, array_values($requests), JSON_PRETTY_PRINT);
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
    $lines    = read_htpasswd_lines();
    $usernames = array_values(array_filter(array_map(fn($l) => explode(':', $l)[0], $lines)));

    $log_file    = __DIR__ . '/../data/login_log.json';
    $log         = file_exists($log_file) ? (json_decode(file_get_contents($log_file), true) ?: []) : [];
    $last_logins = [];
    foreach ($log as $entry) {
        if (!empty($entry['ok']) && !empty($entry['user']) && !isset($last_logins[$entry['user']])) {
            $last_logins[$entry['user']] = $entry['ts'];
        }
    }

    $users = array_map(fn($u) => [
        'username'   => $u,
        'last_login' => $last_logins[$u] ?? null,
        'email'      => get_user_email($u) ?? '',
    ], $usernames);
    echo json_encode(['users' => $users]);

} elseif ($action === 'approve') {
    $username = preg_replace('/[^a-zA-Z0-9_\-]/', '', $body['username'] ?? '');
    if (!$username) { http_response_code(400); echo json_encode(['error' => 'No username']); exit; }
    if (in_array(strtolower($username), RESERVED_USERNAMES, true)) {
        http_response_code(400); echo json_encode(['error' => 'That username is reserved.']); exit;
    }

    // Find the pending request to check for a pre-hashed password
    $requests     = load_requests($requests_file);
    $stored_hash  = null;
    $stored_email = null;
    foreach ($requests as $r) {
        if ($r['username'] === $username && $r['status'] === 'pending') {
            $stored_hash  = $r['password_hash'] ?? null;
            $stored_email = $r['email'] ?? null;
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
    if ($stored_email) set_user_email($username, $stored_email);
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

} elseif ($action === 'reset_password') {
    $username = preg_replace('/[^a-zA-Z0-9_\-]/', '', $body['username'] ?? '');
    if (!$username) { http_response_code(400); echo json_encode(['error' => 'No username']); exit; }

    $lines = read_htpasswd_lines();
    $exists = false;
    foreach ($lines as $line) {
        if (str_starts_with($line, $username . ':')) { $exists = true; break; }
    }
    if (!$exists) { http_response_code(400); echo json_encode(['error' => 'No such user']); exit; }

    $new_password = substr(str_replace(['+','/','='], '', base64_encode(random_bytes(16))), 0, 16);
    if (!write_htpasswd(HTPASSWD_FILE, $username, $new_password)) {
        echo json_encode(['error' => 'Could not write to .htpasswd — check the path in config.php']);
        exit;
    }
    echo json_encode(['ok' => true, 'username' => $username, 'password' => $new_password]);

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

    // Remove any stored email
    $emails_file = __DIR__ . '/../data/user_emails.json';
    if (file_exists($emails_file)) {
        $emails = json_decode(file_get_contents($emails_file), true) ?: [];
        if (array_key_exists($username, $emails)) {
            unset($emails[$username]);
            file_put_contents($emails_file, json_encode($emails, JSON_PRETTY_PRINT), LOCK_EX);
        }
    }

    echo json_encode(['ok' => true]);

} else {
    http_response_code(400);
    echo json_encode(['error' => 'Unknown action']);
}
