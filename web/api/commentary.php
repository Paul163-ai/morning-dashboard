<?php
// Bible commentary for one chapter, from the Free Use Bible API (bible.helloao.org).
// The upstream JSON is trimmed to what the Bible tab shows and cached on disk under
// data/commentary_cache/{commentary}/{BOOK}/{chapter}.json, so each chapter is fetched
// once and keeps working if the API is down. Chapters a commentary doesn't cover
// (upstream 404) are cached as {"missing": true}.
// Desktop counterpart: fetch_commentary_chapter() in dashboard.py (same trimmed format).
header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../helpers.php';
session_write_close();

const COMMENTARIES = [
    'matthew-henry', 'john-calvin', 'jamieson-fausset-brown', 'john-gill',
    'adam-clarke', 'keil-delitzsch', 'tyndale',
];

$commentary = (string)($_GET['commentary'] ?? '');
$book_id    = preg_replace('/[^A-Z0-9]/', '', strtoupper((string)($_GET['book_id'] ?? '')));
$chapter    = (int)($_GET['chapter'] ?? 0);

if (!in_array($commentary, COMMENTARIES, true) || !preg_match('/^[1-3A-Z][A-Z0-9]{2}$/', $book_id)
    || $chapter < 1 || $chapter > 150) {
    http_response_code(400);
    echo json_encode(['error' => 'Invalid request']);
    exit;
}

// helloao uses NAM for Nahum; the rest of the app uses NAH.
$api_book = $book_id === 'NAH' ? 'NAM' : $book_id;

$cache_file = __DIR__ . "/../data/commentary_cache/$commentary/$book_id/$chapter.json";
if (is_file($cache_file)) {
    $cached = file_get_contents($cache_file);
    if ($cached !== false && json_decode($cached) !== null) { echo $cached; exit; }
}

$ch = curl_init("https://bible.helloao.org/api/c/$commentary/$api_book/$chapter.json");
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT        => 15,
    CURLOPT_FOLLOWLOCATION => true,
    CURLOPT_USERAGENT      => 'MorningDashboard/2.0',
    CURLOPT_SSL_VERIFYPEER => true,
]);
$body = curl_exec($ch);
$code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

$data = ($body !== false && $code === 200) ? json_decode($body, true) : null;

if ($code === 404) {
    $out = ['missing' => true];
} elseif (!is_array($data) || !isset($data['chapter']['content'])) {
    http_response_code(502);
    echo json_encode(['error' => 'Commentary service unavailable — try again later.']);
    exit;
} else {
    $sections = [];
    foreach ($data['chapter']['content'] as $item) {
        if (($item['type'] ?? '') !== 'verse' || !isset($item['number'])) continue;
        $parts = array_filter(array_map(fn($p) => is_string($p) ? trim($p) : '', (array)($item['content'] ?? [])), 'strlen');
        if (!$parts) continue;
        $sections[] = ['verse' => (int)$item['number'], 'text' => implode("\n", $parts)];
    }
    $info = $data['commentary'] ?? [];
    $out = [
        'name'        => (string)($info['name'] ?? $commentary),
        'website'     => (string)($info['website'] ?? ''),
        'license_url' => (string)($info['licenseUrl'] ?? ''),
        // The book introduction is only shown with chapter 1
        'book_intro'  => $chapter === 1 ? trim((string)($data['book']['introduction'] ?? '')) : '',
        'intro'       => trim((string)($data['chapter']['introduction'] ?? '')),
        'sections'    => $sections,
    ];
}

$flags = JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES;
$dir   = dirname($cache_file);
if (is_dir($dir) || @mkdir($dir, 0755, true)) save_json($cache_file, $out, $flags);
echo json_encode($out, $flags | JSON_INVALID_UTF8_SUBSTITUTE);
