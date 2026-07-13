<?php
header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../helpers.php';

$date_str = $_GET['date'] ?? date('Y-m-d');
try { $date = new DateTime($date_str); } catch (Exception $e) { $date = new DateTime(); }

// Content is keyed by day-of-year, not by calendar year (the frontmatter's
// `date:` field uses a fixed reference year just to be human-readable).
// Reconstruct the month/day against a fixed non-leap year so every calendar
// year maps consistently; Feb 29 has no equivalent in a non-leap year, so
// DateTime naturally overflows it to Mar 1, which is an acceptable fallback.
$ref = DateTime::createFromFormat('Y-m-d', '2025-' . $date->format('m-d'));
$day = (int)$ref->format('z') + 1;

$file = __DIR__ . '/../Systematics/day-' . str_pad((string)$day, 3, '0', STR_PAD_LEFT) . '.md';

if (!file_exists($file)) {
    echo json_encode(['available' => false, 'day' => $day], JSON_UNESCAPED_UNICODE);
    exit;
}

$raw = file_get_contents($file);

$meta = [];
$body = $raw;
if (preg_match('/^---\s*\n(.*?)\n---\s*\n(.*)$/s', $raw, $m)) {
    foreach (explode("\n", $m[1]) as $line) {
        if (preg_match('/^([a-zA-Z_]+):\s*(.*)$/', $line, $kv)) {
            $meta[$kv[1]] = trim($kv[2], " \t\"");
        }
    }
    $body = $m[2];
}

// Split the body on level-2 headings into named sections.
$sections = [];
$parts = preg_split('/^##\s+(.+)$/m', $body, -1, PREG_SPLIT_DELIM_CAPTURE);
// $parts[0] is any text before the first heading (ignored); then alternating [heading, content, heading, content...]
for ($i = 1; $i < count($parts); $i += 2) {
    $heading = trim($parts[$i]);
    $content = trim($parts[$i + 1] ?? '');
    $sections[$heading] = $content;
}

echo json_encode([
    'available' => true,
    'day'       => $day,
    'title'     => $meta['title']   ?? '',
    'section'   => $meta['section'] ?? '',
    'sections'  => $sections,
], JSON_UNESCAPED_UNICODE);
