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

// ESV (api.esv.org) — one site-wide key, kept out of git in data/esv_api_key.txt.
// Crossway's terms require the copyright notice and a link to esv.org on every page showing the text.
$ESV_CITATION = 'Scripture quotations are from the ESV® Bible (The Holy Bible, English Standard Version®), '
              . '© 2001 by Crossway, a publishing ministry of Good News Publishers. Used by permission. All rights reserved.';
$ESV_BOOKS = ['GEN','EXO','LEV','NUM','DEU','JOS','JDG','RUT','1SA','2SA','1KI','2KI','1CH','2CH','EZR','NEH',
              'EST','JOB','PSA','PRO','ECC','SNG','ISA','JER','LAM','EZK','DAN','HOS','JOL','AMO','OBA','JON',
              'MIC','NAH','HAB','ZEP','HAG','ZEC','MAL','MAT','MRK','LUK','JHN','ACT','ROM','1CO','2CO','GAL',
              'EPH','PHP','COL','1TH','2TH','1TI','2TI','TIT','PHM','HEB','JAS','1PE','2PE','1JN','2JN','3JN',
              'JUD','REV'];

$book_id     = preg_replace('/[^A-Z0-9]/', '', strtoupper($_GET['book_id']     ?? 'GEN'));
$chapter     = max(1, (int)($_GET['chapter']     ?? 1));
$translation = $_GET['translation'] ?? 'web';

// Read API key server-side — never trust the browser with it. Guests have no
// prefs of their own, so they never get a key (and no user dir is created).
require_once __DIR__ . '/../helpers.php';
$api_key = '';
if (is_authenticated()) {
    $prefs_file = user_data_dir() . '/prefs.json';
    $prefs      = file_exists($prefs_file) ? (json_decode(file_get_contents($prefs_file), true) ?: []) : [];
    $api_key    = trim($prefs['api_bible_key'] ?? '');
}

// Release the session lock before the slow upstream fetches below — see spurgeon.php.
session_write_close();

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
    if ($translation === 'esv') {
        $book_num = array_search($book_id, $ESV_BOOKS, true);
        if ($book_num === false) throw new RuntimeException('Unknown book');
        $esv_key_file = __DIR__ . '/../data/esv_api_key.txt';
        $esv_key = file_exists($esv_key_file) ? trim(file_get_contents($esv_key_file)) : '';
        if (!$esv_key) throw new RuntimeException('ESV is not set up on this server yet.');

        // Verse-ID range (BBCCCVVV) covers the whole chapter, including single-chapter books,
        // where "Jude 1" would mean verse 1.
        $base = sprintf('%02d%03d', $book_num + 1, $chapter);
        $url  = 'https://api.esv.org/v3/passage/text/?' . http_build_query([
            'q'                           => "{$base}001-{$base}999",
            'include-passage-references'  => 'false',
            'include-first-verse-numbers' => 'true',
            'include-footnotes'           => 'false',
            'include-footnote-body'       => 'false',
            'include-headings'            => 'false',
            'include-short-copyright'     => 'false',
            'indent-poetry'               => 'false',
            'indent-paragraphs'           => '0',
        ]);
        $result = curl_get_json($url, ["Authorization: Token $esv_key"]);
        if ($result['code'] === 401 || $result['code'] === 403) throw new RuntimeException('The server\'s ESV key was rejected.');
        if ($result['code'] === 429) throw new RuntimeException('ESV request limit reached — try again shortly.');
        if ($result['code'] !== 200) throw new RuntimeException("HTTP {$result['code']}");

        // Text format: "[1] In the beginning… [2] The earth…"
        $content = implode(' ', $result['body']['passages'] ?? []);
        // Psalm 119's acrostic letter headings sit on lines of their own; drop them so
        // "Beth" isn't glued to the end of verse 8.
        $content = preg_replace('/^\s*(Aleph|Beth|Gimel|Daleth|He|Waw|Zayin|Heth|Teth|Yodh|Kaph|Lamedh|Mem|Nun|Samekh|Ayin|Pe|Tsadhe|Qoph|Resh|Shin|Taw)\s*$/m', '', $content);
        $verses  = [];
        preg_match_all('/\[(\d+)\]\s*(.*?)(?=\[\d+\]|$)/s', $content, $m, PREG_SET_ORDER);
        foreach ($m as $match) {
            $text = trim(preg_replace('/\s+/', ' ', $match[2]));
            if ($text) $verses[] = ['verse' => (int)$match[1], 'text' => $text];
        }
        if (!$verses) throw new RuntimeException('No verses returned');
        echo json_encode(['verses' => $verses, 'citation' => $ESV_CITATION, 'citation_url' => 'https://www.esv.org'],
                         JSON_UNESCAPED_UNICODE);
    } elseif (str_starts_with($translation, 'apibible:')) {
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
        // bible-api.com codes are short lowercase ids (web, kjv, oeb-cw…);
        // anything else would be injected into the upstream URL path.
        if (!preg_match('/^[a-z0-9-]{2,12}$/', $translation)) throw new RuntimeException('Unknown translation');
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
