<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Request Access — Morning Dashboard</title>
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e; color: #e0e0e0;
            display: flex; align-items: center; justify-content: center;
            min-height: 100vh; padding: 20px;
        }
        .card {
            background: #16213e; border: 1px solid #0f3460;
            border-radius: 12px; padding: 32px; width: 100%; max-width: 440px;
        }
        h1 { font-size: 20px; margin-bottom: 6px; }
        .subtitle { font-size: 13px; color: #a0a0c0; margin-bottom: 24px; }
        label { display: block; font-size: 13px; color: #a0a0c0; margin-bottom: 5px; margin-top: 14px; }
        input, textarea {
            width: 100%; background: #0f3460; color: #e0e0e0;
            border: 1px solid #0f3460; border-radius: 6px;
            padding: 8px 12px; font-size: 14px; font-family: inherit;
        }
        textarea { resize: vertical; min-height: 80px; }
        input:focus, textarea:focus { outline: 2px solid #e94560; }
        button {
            width: 100%; margin-top: 20px; padding: 10px;
            background: #e94560; color: #fff; border: none;
            border-radius: 6px; font-size: 14px; cursor: pointer;
        }
        button:hover { opacity: 0.85; }
        .message { padding: 12px; border-radius: 6px; margin-bottom: 16px; font-size: 13px; }
        .message.success { background: #1a3a1a; color: #66bb6a; border: 1px solid #66bb6a; }
        .message.error   { background: #3a1a1a; color: #ef5350; border: 1px solid #ef5350; }
    </style>
</head>
<body>
<?php
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/helpers.php';

$requests_file   = __DIR__ . '/data/access_requests.json';
$rate_limit_file = __DIR__ . '/data/rate_limit.json';
$message      = '';
$message_type = '';
$submitted    = false;

function check_rate_limit(string $file, string $ip, int $max = 3, int $window = 3600): bool {
    $data = file_exists($file) ? (json_decode(file_get_contents($file), true) ?: []) : [];
    $now  = time();
    // Clean old entries
    $data = array_filter($data, fn($t) => ($now - $t) < $window);
    $ip_entries = array_filter($data, fn($t, $k) => $k === $ip || str_starts_with($k, $ip . '_'), ARRAY_FILTER_USE_BOTH);
    if (count($ip_entries) >= $max) return false;
    $data[$ip . '_' . $now] = $now;
    file_put_contents($file, json_encode($data));
    return true;
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $ip = $_SERVER['REMOTE_ADDR'] ?? 'unknown';
    if (!check_rate_limit($rate_limit_file, $ip)) {
        $message = 'Too many requests — please try again later.';
        $message_type = 'error';
        goto render;
    }
    $username = preg_replace('/[^a-zA-Z0-9_\-]/', '', trim($_POST['username'] ?? ''));
    $name     = substr(strip_tags(trim($_POST['name']     ?? '')), 0, 100);
    $email    = substr(strip_tags(trim($_POST['email']    ?? '')), 0, 200);
    $reason   = substr(strip_tags(trim($_POST['reason']   ?? '')), 0, 500);
    $password  = $_POST['password']  ?? '';
    $password2 = $_POST['password2'] ?? '';

    if (!$username || !$name) {
        $message = 'Please fill in your username and name.';
        $message_type = 'error';
    } elseif ($email && !filter_var($email, FILTER_VALIDATE_EMAIL)) {
        $message = 'Please enter a valid email address.';
        $message_type = 'error';
    } elseif (strlen($password) < 8) {
        $message = 'Password must be at least 8 characters.';
        $message_type = 'error';
    } elseif ($password !== $password2) {
        $message = 'Passwords do not match.';
        $message_type = 'error';
    } else {
        $requests = file_exists($requests_file)
            ? (json_decode(file_get_contents($requests_file), true) ?: [])
            : [];

        // Check for duplicate pending request or existing account
        $already = array_filter($requests, fn($r) => $r['username'] === $username && $r['status'] === 'pending');
        $taken = false;
        if (file_exists(HTPASSWD_FILE)) {
            foreach (file(HTPASSWD_FILE, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
                if (str_starts_with($line, $username . ':')) { $taken = true; break; }
            }
        }
        if ($already || $taken) {
            $message = 'That username is already taken.';
            $message_type = 'error';
        } else {
            $requests[] = [
                'username'      => $username,
                'name'          => $name,
                'email'         => $email,
                'reason'        => $reason,
                'password_hash' => apr1_md5($password),
                'requested'     => date('Y-m-d H:i:s'),
                'status'        => 'pending',
            ];
            file_put_contents($requests_file, json_encode($requests, JSON_PRETTY_PRINT));
            $submitted = true;

            $subject = 'Morning Dashboard: access request from ' . $username;
            $body    = "New access request received.\n\n"
                     . "Username: $username\n"
                     . "Name: $name\n"
                     . "Email: " . ($email ?: '(not provided)') . "\n"
                     . "Reason: " . ($reason ?: '(not provided)') . "\n"
                     . "Requested: " . date('Y-m-d H:i:s') . "\n\n"
                     . "Approve or deny via the admin panel.";
            $headers = 'From: Morning Dashboard <' . ADMIN_EMAIL . ">\r\n"
                     . 'Content-Type: text/plain; charset=UTF-8';
            @mail(ADMIN_EMAIL, $subject, $body, $headers);
        }
    }
}
render:
?>
<div class="card">
    <h1>☀️ Request Access</h1>
    <p class="subtitle">Morning Dashboard — fill in the form and the admin will be in touch.</p>

    <?php if ($submitted): ?>
        <div class="message success">
            ✅ Request submitted! Once approved you'll be able to log in with the username and password you chose.
        </div>
    <?php else: ?>
        <?php if ($message): ?>
            <div class="message <?= $message_type ?>"><?= htmlspecialchars($message) ?></div>
        <?php endif; ?>
        <form method="POST">
            <label for="username">Desired username (letters, numbers, - and _ only)</label>
            <input type="text" id="username" name="username" required
                   pattern="[a-zA-Z0-9_\-]+" maxlength="40"
                   value="<?= htmlspecialchars($_POST['username'] ?? '') ?>">

            <label for="name">Your name</label>
            <input type="text" id="name" name="name" required maxlength="100"
                   value="<?= htmlspecialchars($_POST['name'] ?? '') ?>">

            <label for="email">Your email (optional)</label>
            <input type="email" id="email" name="email" maxlength="200"
                   value="<?= htmlspecialchars($_POST['email'] ?? '') ?>">

            <label for="reason">Why would you like access? (optional)</label>
            <textarea id="reason" name="reason" maxlength="500"><?= htmlspecialchars($_POST['reason'] ?? '') ?></textarea>

            <label for="password">Choose a password (at least 8 characters)</label>
            <input type="password" id="password" name="password" required minlength="8" autocomplete="new-password">

            <label for="password2">Confirm password</label>
            <input type="password" id="password2" name="password2" required minlength="8" autocomplete="new-password">

            <button type="submit">Send Request</button>
        </form>
    <?php endif; ?>
</div>
</body>
</html>
