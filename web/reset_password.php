<?php
require_once __DIR__ . '/helpers.php';
if (!empty($_SESSION['user'])) {
    header('Location: /');
    exit;
}

$token   = $_POST['token'] ?? $_GET['token'] ?? '';
$user    = $token !== '' ? validate_password_reset_token($token) : null;
$error   = $user === null ? 'This reset link is invalid or has expired.' : '';

if ($user !== null && $_SERVER['REQUEST_METHOD'] === 'POST') {
    $password  = $_POST['password']  ?? '';
    $password2 = $_POST['password2'] ?? '';
    if (strlen($password) < 8) {
        $error = 'Password must be at least 8 characters.';
    } elseif ($password !== $password2) {
        $error = 'Passwords do not match.';
    } else {
        if (write_htpasswd(HTPASSWD_FILE, $user, $password)) {
            invalidate_password_reset_token($token);
            revoke_logins($user);
            header('Location: /login.php?reset=1');
            exit;
        }
        $error = 'Could not update your password — please try again or contact the admin.';
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reset Password — Morning Dashboard</title>
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
        input[type="password"]:focus { border-color: #4a80c0; }
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
    <div class="title">☀️ Reset Password</div>
    <?php if ($error): ?>
    <div class="error"><?= htmlspecialchars($error) ?></div>
    <?php endif; ?>
    <?php if ($user !== null): ?>
    <form method="post">
        <input type="hidden" name="token" value="<?= htmlspecialchars($token) ?>">
        <label for="password">New password</label>
        <input type="password" id="password" name="password" autocomplete="new-password" minlength="8" autofocus>
        <label for="password2">Confirm new password</label>
        <input type="password" id="password2" name="password2" autocomplete="new-password" minlength="8">
        <button type="submit" class="btn">Set new password</button>
    </form>
    <?php else: ?>
    <a class="back-link" href="/forgot_password.php">&larr; Request a new reset link</a>
    <?php endif; ?>
</div>
</body>
</html>
