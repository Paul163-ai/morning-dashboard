<?php
require_once __DIR__ . '/config.php';

if (session_status() === PHP_SESSION_NONE) {
    ini_set('session.cookie_httponly', '1');
    ini_set('session.cookie_secure', '1');
    ini_set('session.cookie_samesite', 'Lax');
    ini_set('session.gc_maxlifetime', '86400');
    session_start();
}

// Request-scoped user override for Basic Auth requests (desktop app).
// Set by require_auth(); read by current_user(). Not persisted to session.
$_MD_AUTH_USER = null;

function current_user(): string {
    global $_MD_AUTH_USER;
    $user = $_MD_AUTH_USER ?? ($_SESSION['user'] ?? '');
    return preg_replace('/[^a-zA-Z0-9_\-]/', '', $user) ?: 'default';
}

function user_data_dir(): string {
    $base = __DIR__ . '/data/users/' . current_user();
    if (!is_dir($base))            mkdir($base,             0755, true);
    if (!is_dir($base.'/sermons')) mkdir($base.'/sermons',  0755, true);
    return $base;
}

// --- Remember-me tokens ---

function _remember_tokens_file(): string {
    return __DIR__ . '/data/remember_tokens.json';
}

function create_remember_token(string $username): string {
    $token  = bin2hex(random_bytes(32));
    $file   = _remember_tokens_file();
    $tokens = file_exists($file) ? (json_decode(file_get_contents($file), true) ?: []) : [];
    $now    = time();
    foreach ($tokens as $t => $d) {
        if ($d['expires'] < $now) unset($tokens[$t]);
    }
    $tokens[$token] = ['user' => $username, 'expires' => $now + 30 * 24 * 3600];
    file_put_contents($file, json_encode($tokens), LOCK_EX);
    return $token;
}

function validate_remember_token(string $token): ?string {
    $file = _remember_tokens_file();
    if (!file_exists($file)) return null;
    $tokens = json_decode(file_get_contents($file), true) ?: [];
    $data   = $tokens[$token] ?? null;
    if (!$data) return null;
    if ($data['expires'] < time()) {
        unset($tokens[$token]);
        file_put_contents($file, json_encode($tokens), LOCK_EX);
        return null;
    }
    return preg_replace('/[^a-zA-Z0-9_\-]/', '', $data['user'] ?? '') ?: null;
}

function invalidate_remember_token(string $token): void {
    $file = _remember_tokens_file();
    if (!file_exists($file)) return;
    $tokens = json_decode(file_get_contents($file), true) ?: [];
    if (array_key_exists($token, $tokens)) {
        unset($tokens[$token]);
        file_put_contents($file, json_encode($tokens), LOCK_EX);
    }
}

// --- Login log ---

function log_login_event(string $user, string $ip, string $method, bool $ok): void {
    $file    = __DIR__ . '/data/login_log.json';
    $entries = file_exists($file) ? (json_decode(file_get_contents($file), true) ?: []) : [];
    array_unshift($entries, ['ts' => time(), 'user' => $user, 'ip' => $ip, 'method' => $method, 'ok' => $ok]);
    if (count($entries) > 200) $entries = array_slice($entries, 0, 200);
    file_put_contents($file, json_encode($entries), LOCK_EX);
}

// --- Auth ---

function verify_htpasswd(string $username, string $password): bool {
    $username = preg_replace('/[^a-zA-Z0-9_\-]/', '', $username);
    if (!$username || $password === '') return false;
    if (!file_exists(HTPASSWD_FILE)) return false;
    foreach (file(HTPASSWD_FILE, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        if (!str_starts_with($line, $username . ':')) continue;
        return _verify_hash($password, substr($line, strlen($username) + 1));
    }
    return false;
}

function _verify_hash(string $password, string $stored): bool {
    if (str_starts_with($stored, '$apr1$')) {
        $parts = explode('$', $stored);
        return count($parts) >= 4 && hash_equals(apr1_md5($password, $parts[2]), $stored);
    }
    return hash_equals(crypt($password, $stored), $stored);
}

function _get_basic_auth_credentials(): ?array {
    if (!empty($_SERVER['PHP_AUTH_USER'])) {
        return [$_SERVER['PHP_AUTH_USER'], $_SERVER['PHP_AUTH_PW'] ?? ''];
    }
    $auth = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
    if (str_starts_with($auth, 'Basic ')) {
        $decoded = base64_decode(substr($auth, 6), true);
        if ($decoded !== false) {
            $pos = strpos($decoded, ':');
            if ($pos !== false) {
                return [substr($decoded, 0, $pos), substr($decoded, $pos + 1)];
            }
        }
    }
    return null;
}

function _is_api_request(): bool {
    return str_contains($_SERVER['SCRIPT_FILENAME'] ?? '', DIRECTORY_SEPARATOR . 'api' . DIRECTORY_SEPARATOR);
}

function require_auth(): void {
    global $_MD_AUTH_USER;

    if (!empty($_SESSION['user'])) return;

    // Check remember-me cookie
    $token = $_COOKIE['remember_me'] ?? '';
    if ($token !== '') {
        $user = validate_remember_token($token);
        if ($user !== null) {
            invalidate_remember_token($token);
            $new_token = create_remember_token($user);
            setcookie('remember_me', $new_token, ['expires' => time() + 30 * 24 * 3600, 'path' => '/', 'secure' => true, 'httponly' => true, 'samesite' => 'Lax']);
            $_SESSION['user'] = $user;
            log_login_event($user, $_SERVER['REMOTE_ADDR'] ?? 'unknown', 'remember', true);
            return;
        }
        // Expired/invalid — clear it
        setcookie('remember_me', '', ['expires' => 1, 'path' => '/', 'secure' => true, 'httponly' => true, 'samesite' => 'Lax']);
    }

    // Check HTTP Basic Auth (desktop app / programmatic access)
    $creds = _get_basic_auth_credentials();
    if ($creds !== null) {
        [$user, $pass] = $creds;
        if (verify_htpasswd($user, $pass)) {
            $_MD_AUTH_USER = $user;
            return;
        }
    }

    // Not authenticated
    $script = basename($_SERVER['SCRIPT_FILENAME'] ?? '');
    if (in_array($script, ['login.php', 'request.php', 'setup.php'])) return;

    if (_is_api_request()) {
        if (!headers_sent()) header('Content-Type: application/json; charset=utf-8');
        http_response_code(401);
        echo json_encode(['error' => 'Not authenticated']);
        exit;
    }
    header('Location: /login.php');
    exit;
}

require_auth();

// CSRF: for session-authenticated POST/DELETE/PUT requests, require the custom header.
// Basic Auth requests from the desktop app ($_MD_AUTH_USER !== null) are exempt.
// Unauthenticated public pages (login.php, request.php) have no session, so also exempt.
if ($_MD_AUTH_USER === null && !empty($_SESSION['user'])) {
    $method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
    if (in_array($method, ['POST', 'DELETE', 'PUT', 'PATCH'])) {
        if (strtolower($_SERVER['HTTP_X_REQUESTED_WITH'] ?? '') !== 'xmlhttprequest') {
            if (!headers_sent()) header('Content-Type: application/json; charset=utf-8');
            http_response_code(403);
            echo json_encode(['error' => 'CSRF check failed']);
            exit;
        }
    }
}

// --- APR1-MD5 (accepts optional $salt for hash verification) ---

function apr1_md5(string $password, string $salt = ''): string {
    $chars = './0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';
    $to64  = function (int $v, int $n) use ($chars): string {
        $out = '';
        while (--$n >= 0) { $out .= $chars[$v & 0x3f]; $v >>= 6; }
        return $out;
    };

    if ($salt === '') {
        $salt = substr(strtr(base64_encode(random_bytes(6)), '+', '.'), 0, 8);
    }
    $len = strlen($password);

    $ctx = $password . '$apr1$' . $salt;
    $bin = md5($password . $salt . $password, true);
    for ($i = $len; $i > 0; $i -= 16) $ctx .= substr($bin, 0, min(16, $i));
    for ($i = $len; $i > 0; $i >>= 1) $ctx .= ($i & 1) ? "\0" : $password[0];
    $bin = md5($ctx, true);

    for ($i = 0; $i < 1000; $i++) {
        $c = ($i & 1) ? $password : $bin;
        if ($i % 3) $c .= $salt;
        if ($i % 7) $c .= $password;
        $c  .= ($i & 1) ? $bin : $password;
        $bin = md5($c, true);
    }

    $hash  = $to64((ord($bin[ 0]) << 16) | (ord($bin[ 6]) << 8) | ord($bin[12]), 4);
    $hash .= $to64((ord($bin[ 1]) << 16) | (ord($bin[ 7]) << 8) | ord($bin[13]), 4);
    $hash .= $to64((ord($bin[ 2]) << 16) | (ord($bin[ 8]) << 8) | ord($bin[14]), 4);
    $hash .= $to64((ord($bin[ 3]) << 16) | (ord($bin[ 9]) << 8) | ord($bin[15]), 4);
    $hash .= $to64((ord($bin[ 4]) << 16) | (ord($bin[10]) << 8) | ord($bin[ 5]), 4);
    $hash .= $to64(ord($bin[11]), 2);

    return '$apr1$' . $salt . '$' . $hash;
}

function write_htpasswd_prehashed(string $file, string $username, string $hash): bool {
    $new_line = $username . ':' . $hash;
    $lines    = file_exists($file)
        ? file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES)
        : [];
    $found = false;
    foreach ($lines as &$line) {
        if (str_starts_with($line, $username . ':')) { $line = $new_line; $found = true; break; }
    }
    if (!$found) $lines[] = $new_line;
    return file_put_contents($file, implode("\n", $lines) . "\n") !== false;
}

function write_htpasswd(string $file, string $username, string $password): bool {
    $new_line = $username . ':' . apr1_md5($password);
    $lines    = file_exists($file)
        ? file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES)
        : [];
    $found = false;
    foreach ($lines as &$line) {
        if (str_starts_with($line, $username . ':')) { $line = $new_line; $found = true; break; }
    }
    if (!$found) $lines[] = $new_line;
    return file_put_contents($file, implode("\n", $lines) . "\n") !== false;
}
