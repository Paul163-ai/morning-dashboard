<?php
header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../helpers.php';

// Release the session lock before the slow scrape below — otherwise every
// other API request from this session (notes, comments, prefs...) blocks
// until this one finishes, which can make the whole tab appear to hang.
session_write_close();

$date_str = $_GET['date'] ?? date('Y-m-d');
try { $date = new DateTime($date_str); } catch (Exception $e) { $date = new DateTime(); }

$month = $date->format('m');
$day   = $date->format('d');

// The romans45.org reading for a given month/day is the same every year, so
// cache by month-day to avoid re-scraping on every request.
$cache_file = __DIR__ . '/../data/spurgeon_original_cache.json';
$cache_key  = "{$month}-{$day}";
$cache      = file_exists($cache_file) ? (json_decode(file_get_contents($cache_file), true) ?: []) : [];

if (isset($cache[$cache_key])) {
    echo json_encode(['readings' => $cache[$cache_key]], JSON_UNESCAPED_UNICODE);
    exit;
}

function curl_fetch(string $url, array $headers = []): string {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 15,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_USERAGENT      => 'MorningDashboard/2.0',
        CURLOPT_SSL_VERIFYPEER => true,
        CURLOPT_HTTPHEADER     => $headers,
    ]);
    $result = curl_exec($ch);
    $err    = curl_error($ch);
    curl_close($ch);
    if ($err) throw new RuntimeException("curl: $err");
    if ($result === false) throw new RuntimeException("curl returned false");
    return $result;
}

$results = [];
try {
    $html = curl_fetch('https://www.romans45.org/morn_eve/m_e.html');

    foreach ([['AM', '☀️ Morning'], ['PM', '🌙 Evening']] as [$period, $label]) {
        $anchor = "{$month}/{$day}/{$period}";
        $pos = strpos($html, '"' . $anchor . '"');
        if ($pos === false) $pos = strpos($html, "'" . $anchor . "'");
        if ($pos === false) {
            $results[] = ['label' => $label, 'text' => 'Reading not found.'];
            continue;
        }

        // Boundary: next date anchor
        if (preg_match('/"\d\d\/\d\d\/[AP]M"/', $html, $m, PREG_OFFSET_CAPTURE, $pos + 10)) {
            $chunk = substr($html, $pos, $m[0][1] - $pos);
        } else {
            $chunk = substr($html, $pos, 6000);
        }

        // Replace decorative initial-letter images with the actual letter
        $chunk = preg_replace_callback(
            '/<img[^>]+\/images\/([a-z])\.gif[^>]*>/i',
            fn($m) => strtoupper($m[1]),
            $chunk
        );

        // Strip scripts/styles/tags
        $chunk = preg_replace('/<script[^>]*>.*?<\/script>/is', '', $chunk);
        $chunk = preg_replace('/<style[^>]*>.*?<\/style>/is',  '', $chunk);
        $text  = strip_tags($chunk);
        $text  = html_entity_decode($text, ENT_QUOTES | ENT_HTML5, 'UTF-8');
        // Map Windows-1252 numeric entities (&#128;–&#159;) that html_entity_decode leaves as-is
        $win1252 = [128=>"\u{20AC}",130=>"\u{201A}",131=>"\u{0192}",132=>"\u{201E}",
                    133=>"\u{2026}",134=>"\u{2020}",135=>"\u{2021}",136=>"\u{02C6}",
                    137=>"\u{2030}",138=>"\u{0160}",139=>"\u{2039}",140=>"\u{0152}",
                    142=>"\u{017D}",145=>"\u{2018}",146=>"\u{2019}",147=>"\u{201C}",
                    148=>"\u{201D}",149=>"\u{2022}",150=>"\u{2013}",151=>"\u{2014}",
                    152=>"\u{02DC}",153=>"\u{2122}",154=>"\u{0161}",155=>"\u{203A}",
                    156=>"\u{0153}",158=>"\u{017E}",159=>"\u{0178}"];
        $text  = preg_replace_callback('/&#(\d+);/', function ($m) use ($win1252) {
            $cp = (int)$m[1];
            return $win1252[$cp] ?? mb_chr($cp, 'UTF-8');
        }, $text);
        $text  = preg_replace('/\s+/', ' ', $text);
        $text  = trim($text);

        if (strlen($text) > 50) {
            $text = preg_replace('/^[^>]*>\s*/', '', $text);
            $text = substr($text, 0, 3000);
            $results[] = ['label' => $label, 'text' => $text];
        } else {
            $results[] = ['label' => $label, 'text' => 'Reading not available.'];
        }
    }
} catch (Exception $e) {
    $results = [['label' => 'Error', 'text' => 'Could not load reading: ' . $e->getMessage()]];
}

$valid = !empty($results) && !array_filter($results, fn($r) =>
    $r['label'] === 'Error' || in_array($r['text'], ['Reading not found.', 'Reading not available.'])
);
if ($valid) {
    $cache[$cache_key] = $results;
    file_put_contents($cache_file, json_encode($cache, JSON_UNESCAPED_UNICODE), LOCK_EX);
}

echo json_encode(['readings' => $results], JSON_UNESCAPED_UNICODE);
