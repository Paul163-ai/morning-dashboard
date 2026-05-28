<?php
header('Content-Type: application/json; charset=utf-8');

$APIBIBLE_IDS = [
    'CSB' => 'a556c5305ee15c3f-01',
    'NLT' => 'd6e14a625393b4da-01',
    'NIV' => '3e2eb613d45e131e-01',
];

$APIBIBLE_CITATIONS = [
    'CSB' => 'Christian Standard Bible® and CSB® are federally registered trademarks of Holman Bible Publishers. All rights reserved.',
    'NLT' => 'Holy Bible, New Living Translation, Copyright © 2014, Tyndale House Publishers. All rights reserved.',
    'NIV' => 'The Holy Bible, New International Version® NIV® Copyright © 1973, 1978, 1984, 2011 by Biblica, Inc.® All rights reserved worldwide.',
];

$book_id     = preg_replace('/[^A-Z0-9]/', '', strtoupper($_GET['book_id']     ?? 'GEN'));
$chapter     = max(1, (int)($_GET['chapter']     ?? 1));
$translation = $_GET['translation'] ?? 'web';

// Read API key server-side — never trust the browser with it
require_once __DIR__ . '/../helpers.php';
$prefs_file = user_data_dir() . '/prefs.json';
$prefs      = file_exists($prefs_file) ? (json_decode(file_get_contents($prefs_file), true) ?: []) : [];
$api_key    = trim($prefs['api_bible_key'] ?? '');

function curl_get_json(string $url, array $headers = []): array {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 10,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_USERAGENT      => 'MorningDashboard/2.0',
        CURLOPT_SSL_VERIFYPEER => true,
        CURLOPT_HTTPHEADER     => $headers,
    ]);
    $body = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    if (!$body) throw new RuntimeException('No response');
    $data = json_decode($body, true);
    return ['body' => $data, 'code' => $code];
}

try {
    if (str_starts_with($translation, 'apibible:')) {
        $bible_name = substr($translation, 9);
        $bible_id   = $APIBIBLE_IDS[$bible_name] ?? null;
        if (!$bible_id) throw new RuntimeException("Unknown translation: $bible_name");
        if (!$api_key) throw new RuntimeException('No API.Bible key — add one in Settings.');

        $chapter_id = "{$book_id}.{$chapter}";
        $url = "https://rest.api.bible/v1/bibles/{$bible_id}/chapters/{$chapter_id}"
             . "?content-type=text&include-verse-numbers=true&include-chapter-numbers=false"
             . "&include-titles=false&include-notes=false";

        $result = curl_get_json($url, ["api-key: $api_key"]);
        if ($result['code'] === 401) throw new RuntimeException('Invalid API.Bible key — check your key in Settings.');
        if ($result['code'] !== 200) throw new RuntimeException("HTTP {$result['code']}");

        $content = $result['body']['data']['content'] ?? '';
        // Parse verse numbers from text content (format: "[1] text [2] more text")
        $verses = [];
        preg_match_all('/\[(\d+)\]\s*(.*?)(?=\[\d+\]|$)/s', $content, $m, PREG_SET_ORDER);
        foreach ($m as $match) {
            $text = trim(preg_replace('/\s+/', ' ', $match[2]));
            if ($text) $verses[] = ['verse' => (int)$match[1], 'text' => $text];
        }
        if (!$verses) {
            // Fallback: return raw content split into paragraphs
            $paras = array_filter(array_map('trim', preg_split('/\n{2,}/', $content)));
            echo json_encode(['raw_paragraphs' => array_values($paras),
                              'citation' => $APIBIBLE_CITATIONS[$bible_name] ?? '']);
            exit;
        }
        echo json_encode(['verses' => $verses, 'citation' => $APIBIBLE_CITATIONS[$bible_name] ?? ''],
                         JSON_UNESCAPED_UNICODE);
    } else {
        $url    = "https://bible-api.com/data/{$translation}/{$book_id}/{$chapter}";
        $result = curl_get_json($url);
        if ($result['code'] !== 200) throw new RuntimeException("HTTP {$result['code']}");

        $raw_verses = $result['body']['verses'] ?? [];
        if (!$raw_verses) throw new RuntimeException('No verses returned');

        $verses = array_map(fn($v) => [
            'verse' => (int)$v['verse'],
            'text'  => trim($v['text']),
        ], $raw_verses);

        echo json_encode(['verses' => $verses], JSON_UNESCAPED_UNICODE);
    }
} catch (Exception $e) {
    echo json_encode(['error' => $e->getMessage()]);
}
