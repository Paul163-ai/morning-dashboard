<?php
header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../helpers.php';

$SOURCES = [
    'BBC News'    => 'https://feeds.bbci.co.uk/news/rss.xml',
    'Google News' => 'https://news.google.com/rss',
    'Open Doors'  => 'https://www.opendoorsuk.org/feed/',
    'Christianity Today' => 'https://www.christianitytoday.com/feed/',
    'TED Talks'   => 'https://feeds.acast.com/public/shows/67587e77c705e441797aff96',
    'AI News'     => 'https://feeds.feedburner.com/TheHackersNews',
    'Tech News'   => 'https://feeds.bbci.co.uk/news/technology/rss.xml',
];

function fetch_rss(string $url): array {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 10,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_USERAGENT      => 'MorningDashboard/2.0',
        CURLOPT_SSL_VERIFYPEER => true,
    ]);
    $xml = curl_exec($ch);
    curl_close($ch);
    if (!$xml) return [['Could not load feed', '']];

    $items   = [];
    $matches = [];
    preg_match_all('/<item>(.*?)<\/item>/s', $xml, $matches);
    foreach (array_slice($matches[1], 0, 10) as $item) {
        $title = $link = '';
        if (preg_match('/<title>(.*?)<\/title>/s', $item, $m)) {
            $title = html_entity_decode(preg_replace('/<!\[CDATA\[(.*?)\]\]>/s', '$1', $m[1]), ENT_QUOTES, 'UTF-8');
            $title = strip_tags(trim($title));
        }
        if (preg_match('/<link>(.*?)<\/link>/s', $item, $m)) {
            $link = trim($m[1]);
        }
        if ($title) $items[] = [$title, $link];
    }
    return $items ?: [['No items found', '']];
}

$result = [];
foreach ($SOURCES as $name => $url) {
    $result[$name] = fetch_rss($url);
}

echo json_encode(['sources' => $result], JSON_UNESCAPED_UNICODE);
