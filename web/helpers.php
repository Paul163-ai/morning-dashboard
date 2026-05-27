<?php
function current_user(): string {
    $user = preg_replace('/[^a-zA-Z0-9_\-]/', '', $_SERVER['PHP_AUTH_USER'] ?? 'default');
    return $user ?: 'default';
}

function user_data_dir(): string {
    $base = __DIR__ . '/data/users/' . current_user();
    if (!is_dir($base))           mkdir($base,              0755, true);
    if (!is_dir($base.'/sermons')) mkdir($base.'/sermons',   0755, true);
    return $base;
}

// APR1-MD5 hash — the format Apache's own htpasswd tool produces and all versions support
function apr1_md5(string $password): string {
    $chars = './0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';
    $to64  = function (int $v, int $n) use ($chars): string {
        $out = '';
        while (--$n >= 0) { $out .= $chars[$v & 0x3f]; $v >>= 6; }
        return $out;
    };

    $salt = substr(strtr(base64_encode(random_bytes(6)), '+', '.'), 0, 8);
    $len  = strlen($password);

    $ctx  = $password . '$apr1$' . $salt;
    $bin  = md5($password . $salt . $password, true);
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
