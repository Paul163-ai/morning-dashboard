<?php
require_once __DIR__ . '/helpers.php';
if (!empty($_SESSION['user'])) {
    header('Location: /');
    exit;
}

$rate_limit_file = __DIR__ . '/data/rate_limit_reset.json';
$message      = '';
$message_type = '';
$submitted    = false;

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $ip = $_SERVER['REMOTE_ADDR'] ?? 'unknown';
    if (!check_rate_limit($rate_limit_file, $ip)) {
        $message = 'Too many requests — please try again later.';
        $message_type = 'error';
    } else {
        $identifier = trim($_POST['identifier'] ?? '');
        $username   = preg_replace('/[^a-zA-Z0-9_\-]/', '', $identifier);

        // Resolve to a username: try as a literal username first, else by email.
        $resolved = null;
        if ($username && file_exists(HTPASSWD_FILE)) {
            foreach (file(HTPASSWD_FILE, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
                if (str_starts_with($line, $username . ':')) { $resolved = $username; break; }
            }
        }
        if (!$resolved && filter_var($identifier, FILTER_VALIDATE_EMAIL)) {
            $resolved = find_username_by_email($identifier);
        }

        if ($resolved) {
            $email = get_user_email($resolved);
            if ($email) {
                $token = create_password_reset_token($resolved);
                $link  = APP_URL . '/reset_password.php?token=' . $token;
                $subject = 'Morning Dashboard: password reset';
                $body    = "We received a request to reset the password for your Morning Dashboard account ($resolved).\n\n"
                         . "Reset it here (valid for 1 hour):\n$link\n\n"
                         . "If you didn't request this, you can ignore this email.";
                $headers = 'From: Morning Dashboard <' . ADMIN_EMAIL . ">\r\n"
                         . 'Content-Type: text/plain; charset=UTF-8';
                @mail($email, $subject, $body, $headers);
            }
        }

        // Always show the same message, whether or not an account was found,
        // so this form can't be used to enumerate usernames/emails.
        $submitted = true;
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Forgot Password — Morning Dashboard</title>
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
            margin-bottom: 0.5rem;
            text-align: center;
        }
        .subtitle {
            font-size: 0.85rem;
            color: #a0a0c0;
            text-align: center;
            margin-bottom: 1.5rem;
        }
        label {
            display: block;
            font-size: 0.85rem;
            color: #a0a0c0;
            margin-bottom: 0.3rem;
        }
        input[type="text"] {
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
        input[type="text"]:focus { border-color: #4a80c0; }
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
        .error {
            background: rgba(233, 69, 96, 0.15);
            border: 1px solid rgba(233, 69, 96, 0.4);
            border-radius: 6px;
            padding: 0.6rem 0.75rem;
            font-size: 0.9rem;
            color: #ff8099;
            margin-bottom: 1rem;
        }
        .success {
            background: rgba(102, 187, 106, 0.15);
            border: 1px solid rgba(102, 187, 106, 0.4);
            border-radius: 6px;
            padding: 0.6rem 0.75rem;
            font-size: 0.9rem;
            color: #a5d6a7;
        }
        .back-link {
            display: block;
            text-align: center;
            margin-top: 1.25rem;
            font-size: 0.9rem;
            color: #5599ff;
        }
    </style>
</head>
<body>
<div class="card">
    <div class="title">☀️ Forgot Password</div>
    <?php if ($submitted): ?>
        <div class="success">If an account with that username or email exists, we've sent a password reset link to the email on file.</div>
    <?php else: ?>
        <div class="subtitle">Enter your username or email and we'll send you a reset link.</div>
        <?php if ($message): ?>
        <div class="error"><?= htmlspecialchars($message) ?></div>
        <?php endif; ?>
        <form method="post">
            <label for="identifier">Username or email</label>
            <input type="text" id="identifier" name="identifier" autofocus
                   value="<?= htmlspecialchars($_POST['identifier'] ?? '') ?>">
            <button type="submit" class="btn">Send reset link</button>
        </form>
    <?php endif; ?>
    <a class="back-link" href="/login.php">&larr; Back to login</a>
</div>
</body>
</html>
