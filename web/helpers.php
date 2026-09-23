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

// "Remember me" token/cookie lifetime — effectively unlimited (10 years).
const REMEMBER_ME_DURATION = 10 * 365 * 24 * 3600;

// current_user() falls back to 'default' when nobody is logged in, so no real
// account may take that name (checked by request.php and access.php approve).
const RESERVED_USERNAMES = ['default'];

function current_user(): string {
    global $_MD_AUTH_USER;
    $user = $_MD_AUTH_USER ?? ($_SESSION['user'] ?? '');
    return preg_replace('/[^a-zA-Z0-9_\-]/', '', $user) ?: 'default';
}

function is_authenticated(): bool {
    global $_MD_AUTH_USER;
    return $_MD_AUTH_USER !== null || !empty($_SESSION['user']);
}

function user_data_dir(): string {
    $base = __DIR__ . '/data/users/' . current_user();
    if (!is_dir($base))            mkdir($base,             0755, true);
    if (!is_dir($base.'/sermons')) mkdir($base.'/sermons',  0755, true);
    return $base;
}

// --- Safe text/JSON handling ---

// Truncate to $max characters without splitting a multi-byte UTF-8 sequence
// (substr() cuts bytes, and a half character makes json_encode() fail).
function clip_text($s, int $max): string {
    return mb_substr(mb_scrub((string)$s, 'UTF-8'), 0, $max, 'UTF-8');
}

// Replace $file's contents via temp file + rename, so concurrent readers never
// see a half-written file. Keeps the existing file's permissions. Falls back to
// an in-place write if the directory doesn't allow creating the temp file.
function write_file_atomic(string $file, string $content): bool {
    $tmp = $file . '.tmp' . bin2hex(random_bytes(4));
    if (@file_put_contents($tmp, $content) !== false) {
        if (file_exists($file)) @chmod($tmp, fileperms($file) & 0777);
        if (@rename($tmp, $file)) return true;
        @unlink($tmp);
    }
    return file_put_contents($file, $content, LOCK_EX) !== false;
}

// Encode and write JSON, refusing to write if encoding fails — otherwise
// file_put_contents(false) would silently truncate the file to empty.
function save_json(string $file, $data, int $flags = 0): bool {
    $json = json_encode($data, $flags | JSON_INVALID_UTF8_SUBSTITUTE);
    if ($json === false) return false;
    return write_file_atomic($file, $json);
}

function read_json(string $file): array {
    if (!file_exists($file)) return [];
    $data = json_decode(file_get_contents($file), true);
    return is_array($data) ? $data : [];
}

// Run $fn while holding an exclusive lock for $file (on a sidecar .lock file),
// so read-modify-write cycles from concurrent requests can't lose updates.
// If the lock file can't be created, $fn still runs, just unlocked.
function with_file_lock(string $file, callable $fn) {
    $lock = @fopen($file . '.lock', 'c');
    if ($lock) flock($lock, LOCK_EX);
    try {
        return $fn();
    } finally {
        if ($lock) { flock($lock, LOCK_UN); fclose($lock); }
    }
}

// Locked read-modify-write of a shared JSON file. $fn gets the current data
// and returns the new data, or null to leave the file untouched.
function update_json(string $file, callable $fn, int $flags = 0): bool {
    return with_file_lock($file, function () use ($file, $fn, $flags) {
        $new = $fn(read_json($file));
        return $new === null ? true : save_json($file, $new, $flags);
    });
}

// --- Remember-me tokens ---

function _remember_tokens_file(): string {
    return __DIR__ . '/data/remember_tokens.json';
}

function create_remember_token(string $username): string {
    $token = bin2hex(random_bytes(32));
    update_json(_remember_tokens_file(), function ($tokens) use ($token, $username) {
        $now = time();
        foreach ($tokens as $t => $d) {
            if (($d['expires'] ?? 0) < $now) unset($tokens[$t]);
        }
        $tokens[$token] = ['user' => $username, 'expires' => $now + REMEMBER_ME_DURATION];
        return $tokens;
    });
    return $token;
}

function validate_remember_token(string $token): ?string {
    $data = read_json(_remember_tokens_file())[$token] ?? null;
    if (!$data) return null;
    if ($data['expires'] < time()) {
        invalidate_remember_token($token);
        return null;
    }
    return preg_replace('/[^a-zA-Z0-9_\-]/', '', $data['user'] ?? '') ?: null;
}

function invalidate_remember_token(string $token): void {
    update_json(_remember_tokens_file(), function ($tokens) use ($token) {
        if (!array_key_exists($token, $tokens)) return null;
        unset($tokens[$token]);
        return $tokens;
    });
}

// Set a fresh remember-me cookie for $username on this browser.
function issue_remember_cookie(string $username): void {
    setcookie('remember_me', create_remember_token($username), ['expires' => time() + REMEMBER_ME_DURATION, 'path' => '/', 'secure' => true, 'httponly' => true, 'samesite' => 'Lax']);
}

// --- Revoking logins ---
// Sessions record when they logged in ($_SESSION['auth_time']); require_auth()
// drops any session older than the user's last revocation. Used on password
// change/reset and account deletion so other devices are logged out.

function _logins_revoked_file(): string {
    return __DIR__ . '/data/logins_revoked.json';
}

function logins_revoked_at(string $username): int {
    return (int)(read_json(_logins_revoked_file())[$username] ?? 0);
}

function revoke_logins(string $username): void {
    invalidate_all_remember_tokens_for_user($username);
    update_json(_logins_revoked_file(), function ($data) use ($username) {
        $data[$username] = time();
        return $data;
    });
    // A user revoking their own logins (changing their password) stays logged
    // in on this browser, including its remember-me cookie if it had one.
    if (($_SESSION['user'] ?? '') === $username) {
        $_SESSION['auth_time'] = time();
        if (!empty($_COOKIE['remember_me'])) issue_remember_cookie($username);
    }
}

// --- Password reset tokens ---

const PASSWORD_RESET_DURATION = 3600; // 1 hour

function _password_resets_file(): string {
    return __DIR__ . '/data/password_resets.json';
}

function create_password_reset_token(string $username): string {
    $token = bin2hex(random_bytes(32));
    update_json(_password_resets_file(), function ($tokens) use ($token, $username) {
        $now = time();
        foreach ($tokens as $t => $d) {
            if (($d['expires'] ?? 0) < $now) unset($tokens[$t]);
        }
        $tokens[$token] = ['user' => $username, 'expires' => $now + PASSWORD_RESET_DURATION, 'used' => false];
        return $tokens;
    });
    return $token;
}

function validate_password_reset_token(string $token): ?string {
    $data = read_json(_password_resets_file())[$token] ?? null;
    if (!$data || !empty($data['used']) || $data['expires'] < time()) return null;
    return preg_replace('/[^a-zA-Z0-9_\-]/', '', $data['user'] ?? '') ?: null;
}

function invalidate_password_reset_token(string $token): void {
    update_json(_password_resets_file(), function ($tokens) use ($token) {
        if (!isset($tokens[$token])) return null;
        $tokens[$token]['used'] = true;
        return $tokens;
    });
}

function invalidate_all_remember_tokens_for_user(string $username): void {
    update_json(_remember_tokens_file(), function ($tokens) use ($username) {
        $changed = false;
        foreach ($tokens as $t => $d) {
            if (($d['user'] ?? '') === $username) { unset($tokens[$t]); $changed = true; }
        }
        return $changed ? $tokens : null;
    });
}

// --- Per-user email addresses ---

function _user_emails_file(): string {
    return __DIR__ . '/data/user_emails.json';
}

function get_user_email(string $username): ?string {
    return read_json(_user_emails_file())[$username] ?? null;
}

function set_user_email(string $username, string $email): void {
    update_json(_user_emails_file(), function ($emails) use ($username, $email) {
        $emails[$username] = $email;
        return $emails;
    }, JSON_PRETTY_PRINT);
}

// Removes the stored email for $username (used when deleting an account).
function delete_user_email(string $username): void {
    update_json(_user_emails_file(), function ($emails) use ($username) {
        if (!array_key_exists($username, $emails)) return null;
        unset($emails[$username]);
        return $emails;
    }, JSON_PRETTY_PRINT);
}

function find_username_by_email(string $email): ?string {
    $emails = read_json(_user_emails_file());
    foreach ($emails as $username => $stored) {
        if (strcasecmp($stored, $email) === 0) return $username;
    }
    return null;
}

// --- Rate limiting (by IP, used by request.php / forgot_password.php) ---

function check_rate_limit(string $file, string $ip, int $max = 3, int $window = 3600): bool {
    $allowed = false;
    update_json($file, function ($data) use ($ip, $max, $window, &$allowed) {
        $now  = time();
        $data = array_filter($data, fn($t) => ($now - $t) < $window);
        $ip_entries = array_filter($data, fn($t, $k) => $k === $ip || str_starts_with($k, $ip . '_'), ARRAY_FILTER_USE_BOTH);
        if (count($ip_entries) >= $max) return null;
        $key = $ip . '_' . $now;
        for ($n = 1; isset($data[$key]); $n++) $key = $ip . '_' . $now . '_' . $n;
        $data[$key] = $now;
        $allowed = true;
        return $data;
    });
    return $allowed;
}

// --- Login log ---

function log_login_event(string $user, string $ip, string $method, bool $ok): void {
    update_json(__DIR__ . '/data/login_log.json', function ($entries) use ($user, $ip, $method, $ok) {
        array_unshift($entries, ['ts' => time(), 'user' => $user, 'ip' => $ip, 'method' => $method, 'ok' => $ok]);
        return array_slice($entries, 0, 200);
    });
}

// --- Guest visits ---

function record_guest_visit(string $ip): void {
    update_json(__DIR__ . '/data/guest_visits.json', function ($data) use ($ip) {
        $data['total'] = ($data['total'] ?? 0) + 1;
        $data['entries'] = $data['entries'] ?? [];
        array_unshift($data['entries'], ['ts' => time(), 'ip' => $ip]);
        $data['entries'] = array_slice($data['entries'], 0, 200);
        return $data;
    });
}

// --- Failed-login lockout (by IP) ---
// Shared by the login form (login.php) and HTTP Basic Auth in require_auth(),
// so the desktop-app auth path can't be used to bypass the form's lockout.

const LOGIN_ATTEMPTS_FILE = __DIR__ . '/data/login_attempts.json';
const LOGIN_MAX_ATTEMPTS  = 5;
const LOGIN_WINDOW        = 900; // 15 minutes

function _login_attempts(string $ip): int {
    $data   = read_json(LOGIN_ATTEMPTS_FILE);
    $cutoff = time() - LOGIN_WINDOW;
    $count  = 0;
    foreach ($data as $key => $ts) {
        if ($ts >= $cutoff && ($key === $ip || str_starts_with($key, $ip . '_'))) $count++;
    }
    return $count;
}

function _record_failed_attempt(string $ip): void {
    update_json(LOGIN_ATTEMPTS_FILE, function ($data) use ($ip) {
        $now    = time();
        $cutoff = $now - LOGIN_WINDOW;
        $data   = array_filter($data, fn($t) => $t >= $cutoff);
        // Several failures can land in the same second (the desktop app fires
        // requests in parallel), so make each key unique rather than overwrite.
        $key = $ip . '_' . $now;
        for ($n = 1; isset($data[$key]); $n++) $key = $ip . '_' . $now . '_' . $n;
        $data[$key] = $now;
        return $data;
    });
}

function _clear_failed_attempts(string $ip): void {
    update_json(LOGIN_ATTEMPTS_FILE, function ($data) use ($ip) {
        $changed = false;
        foreach (array_keys($data) as $key) {
            if ($key === $ip || str_starts_with($key, $ip . '_')) { unset($data[$key]); $changed = true; }
        }
        return $changed ? $data : null;
    });
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

    if (!empty($_SESSION['user'])) {
        if (($_SESSION['auth_time'] ?? 0) >= logins_revoked_at($_SESSION['user'])) return;
        // Logins revoked since this session started (password changed or
        // account deleted) — drop it and fall through as if logged out.
        unset($_SESSION['user'], $_SESSION['auth_time']);
    }

    // Check remember-me cookie
    $token = $_COOKIE['remember_me'] ?? '';
    if ($token !== '') {
        $user = validate_remember_token($token);
        if ($user !== null) {
            invalidate_remember_token($token);
            issue_remember_cookie($user);
            $_SESSION['user'] = $user;
            $_SESSION['auth_time'] = time();
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
        $ip = $_SERVER['REMOTE_ADDR'] ?? 'unknown';
        $attempts = _login_attempts($ip);
        // Locked out: reject without checking the password, even a correct
        // one, so guessing can't continue during the lockout window.
        if ($attempts >= LOGIN_MAX_ATTEMPTS) {
            if (!headers_sent()) {
                header('Content-Type: application/json; charset=utf-8');
                header('Retry-After: ' . LOGIN_WINDOW);
            }
            http_response_code(429);
            echo json_encode(['error' => 'Too many failed attempts — try again in 15 minutes.']);
            exit;
        }
        if (verify_htpasswd($user, $pass)) {
            if ($attempts > 0) _clear_failed_attempts($ip);
            $_MD_AUTH_USER = $user;
            return;
        }
        _record_failed_attempt($ip);
        log_login_event($user !== '' ? clip_text($user, 64) : '?', $ip, 'basic', false);
    }

    // Not authenticated
    $script = basename($_SERVER['SCRIPT_FILENAME'] ?? '');
    if (in_array($script, ['login.php', 'request.php', 'setup.php', 'index.php', 'forgot_password.php', 'reset_password.php'])) return;

    // Allow guest (logged-out) access to the read-only devotional reading,
    // used by the public view shown on index.php for unauthenticated visitors.
    if (in_array($script, ['spurgeon.php', 'spurgeon_modern.php', 'bible.php', 'systematics.php']) && ($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'GET') return;

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

// Locked read-modify-write of an .htpasswd file: $fn gets its lines (without
// newlines) and returns the new lines.
function update_htpasswd(string $file, callable $fn): bool {
    return with_file_lock($file, function () use ($file, $fn) {
        $lines = file_exists($file)
            ? file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES)
            : [];
        return write_file_atomic($file, implode("\n", $fn($lines)) . "\n");
    });
}

function write_htpasswd_prehashed(string $file, string $username, string $hash): bool {
    $new_line = $username . ':' . $hash;
    return update_htpasswd($file, function ($lines) use ($username, $new_line) {
        foreach ($lines as $i => $line) {
            if (str_starts_with($line, $username . ':')) { $lines[$i] = $new_line; return $lines; }
        }
        $lines[] = $new_line;
        return $lines;
    });
}

function write_htpasswd(string $file, string $username, string $password): bool {
    return write_htpasswd_prehashed($file, $username, apr1_md5($password));
}

function remove_htpasswd_user(string $file, string $username): bool {
    return update_htpasswd($file, fn($lines) =>
        array_values(array_filter($lines, fn($l) => !str_starts_with($l, $username . ':'))));
}
