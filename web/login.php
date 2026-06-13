<?php
require_once __DIR__ . '/helpers.php';
// require_auth() ran above but skips login.php; if session already valid, go home
if (!empty($_SESSION['user'])) {
    header('Location: /');
    exit;
}

define('LOGIN_ATTEMPTS_FILE', __DIR__ . '/data/login_attempts.json');
define('LOGIN_MAX_ATTEMPTS', 5);
define('LOGIN_WINDOW', 900); // 15 minutes

function _login_attempts(string $ip): int {
    if (!file_exists(LOGIN_ATTEMPTS_FILE)) return 0;
    $data = json_decode(file_get_contents(LOGIN_ATTEMPTS_FILE), true) ?: [];
    $cutoff = time() - LOGIN_WINDOW;
    $count  = 0;
    foreach ($data as $key => $ts) {
        if ($ts >= $cutoff && ($key === $ip || str_starts_with($key, $ip . '_'))) $count++;
    }
    return $count;
}

function _record_failed_attempt(string $ip): void {
    $data   = file_exists(LOGIN_ATTEMPTS_FILE) ? (json_decode(file_get_contents(LOGIN_ATTEMPTS_FILE), true) ?: []) : [];
    $now    = time();
    $cutoff = $now - LOGIN_WINDOW;
    $data   = array_filter($data, fn($t) => $t >= $cutoff);
    $data[$ip . '_' . $now] = $now;
    file_put_contents(LOGIN_ATTEMPTS_FILE, json_encode($data), LOCK_EX);
}

function _clear_failed_attempts(string $ip): void {
    if (!file_exists(LOGIN_ATTEMPTS_FILE)) return;
    $data = json_decode(file_get_contents(LOGIN_ATTEMPTS_FILE), true) ?: [];
    foreach (array_keys($data) as $key) {
        if ($key === $ip || str_starts_with($key, $ip . '_')) unset($data[$key]);
    }
    file_put_contents(LOGIN_ATTEMPTS_FILE, json_encode($data), LOCK_EX);
}

$ip      = $_SERVER['REMOTE_ADDR'] ?? 'unknown';
$locked  = _login_attempts($ip) >= LOGIN_MAX_ATTEMPTS;
$error   = $locked ? 'Too many failed attempts — try again in 15 minutes.' : '';

if (!$locked && $_SERVER['REQUEST_METHOD'] === 'POST') {
    $username = trim($_POST['username'] ?? '');
    $password = $_POST['password'] ?? '';
    $remember = !empty($_POST['remember']);

    if ($username !== '' && $password !== '' && verify_htpasswd($username, $password)) {
        _clear_failed_attempts($ip);
        session_regenerate_id(true);
        $_SESSION['user'] = preg_replace('/[^a-zA-Z0-9_\-]/', '', $username);
        log_login_event($_SESSION['user'], $ip, 'form', true);
        if ($remember) {
            $token = create_remember_token($_SESSION['user']);
            setcookie('remember_me', $token, [
                'expires'  => time() + REMEMBER_ME_DURATION,
                'path'     => '/',
                'secure'   => true,
                'httponly' => true,
                'samesite' => 'Lax',
            ]);
        }
        header('Location: /');
        exit;
    }

    _record_failed_attempt($ip);
    log_login_event($username !== '' ? $username : '?', $ip, 'form', false);
    $attempts_left = LOGIN_MAX_ATTEMPTS - _login_attempts($ip);
    $error = $attempts_left > 0
        ? 'Invalid username or password.'
        : 'Too many failed attempts — try again in 15 minutes.';
    $locked = $attempts_left <= 0;
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Morning Dashboard — Login</title>
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #e0e0e0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 2rem;
        }
        .card {
            background: #16213e;
            border: 1px solid #0f3460;
            border-radius: 12px;
            padding: 2rem;
            width: 100%;
            max-width: 360px;
        }
        .title {
            font-size: 1.4rem;
            font-weight: bold;
            margin-bottom: 1.5rem;
            text-align: center;
        }
        label {
            display: block;
            font-size: 0.85rem;
            color: #a0a0c0;
            margin-bottom: 0.3rem;
        }
        input[type="text"],
        input[type="password"] {
            width: 100%;
            padding: 0.6rem 0.75rem;
            background: #0f3460;
            border: 1px solid #1e4080;
            border-radius: 6px;
            color: #e0e0e0;
            font-size: 1rem;
            margin-bottom: 1rem;
            outline: none;
        }
        input[type="text"]:focus,
        input[type="password"]:focus {
            border-color: #4a80c0;
        }
        .remember-row {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 1.25rem;
            font-size: 0.9rem;
            color: #a0a0c0;
            cursor: pointer;
        }
        .remember-row input { width: auto; margin: 0; cursor: pointer; }
        .btn {
            width: 100%;
            padding: 0.65rem;
            background: #e94560;
            border: none;
            border-radius: 6px;
            color: #fff;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
        }
        .btn:hover { background: #c73050; }
        .btn:disabled { background: #555; cursor: not-allowed; }
        .error {
            background: rgba(233, 69, 96, 0.15);
            border: 1px solid rgba(233, 69, 96, 0.4);
            border-radius: 6px;
            padding: 0.6rem 0.75rem;
            font-size: 0.9rem;
            color: #ff8099;
            margin-bottom: 1rem;
        }
        .request-link {
            text-align: center;
            margin-top: 1.25rem;
            font-size: 0.85rem;
            color: #a0a0c0;
        }
        .request-link a { color: #5599ff; }
        .guest-link {
            display: block;
            text-align: center;
            margin-top: 0.75rem;
            padding: 0.65rem;
            border: 1px solid #1e4080;
            border-radius: 6px;
            color: #a0a0c0;
            text-decoration: none;
            font-size: 0.9rem;
        }
        .guest-link:hover { border-color: #4a80c0; color: #e0e0e0; }
    </style>
</head>
<body>
<div class="card">
    <div class="title">☀️ Morning Dashboard</div>
    <?php if ($error): ?>
    <div class="error"><?= htmlspecialchars($error) ?></div>
    <?php endif; ?>
    <form method="post">
        <label for="username">Username</label>
        <input type="text" id="username" name="username" autocomplete="username"
               <?= !$locked ? 'autofocus' : '' ?>
               value="<?= htmlspecialchars($_POST['username'] ?? '') ?>"
               <?= $locked ? 'disabled' : '' ?>>
        <label for="password">Password</label>
        <input type="password" id="password" name="password" autocomplete="current-password"
               <?= $locked ? 'disabled' : '' ?>>
        <label class="remember-row">
            <input type="checkbox" name="remember" <?= !empty($_POST['remember']) ? 'checked' : '' ?>
                   <?= $locked ? 'disabled' : '' ?>>
            Remember me
        </label>
        <button type="submit" class="btn" <?= $locked ? 'disabled' : '' ?>>Log in</button>
    </form>
    <div class="request-link"><a href="/request.php">Request access</a></div>
    <a class="guest-link" href="/">Continue without logging in</a>
</div>
</body>
</html>
