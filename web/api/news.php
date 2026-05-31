<?php
header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../helpers.php';

// proxy=true: fetched via rss2json.com (for feeds behind Cloudflare)
$SOURCES = [
    'BBC News'         => ['url' => 'https://feeds.bbci.co.uk/news/rss.xml',               'proxy' => false],
    'Google News'      => ['url' => 'https://news.google.com/rss',                          'proxy' => false],
    'Open Doors'       => ['url' => 'https://www.opendoorsuk.org/feed/',                    'proxy' => false],
    'Gospel Coalition' => ['url' => 'https://www.thegospelcoalition.org/feed/',             'proxy' => true],
    'AI News'          => ['url' => 'https://feeds.feedburner.com/TheHackersNews',           'proxy' => false],
    'Tech News'        => ['url' => 'https://feeds.bbci.co.uk/news/technology/rss.xml',     'proxy' => false],
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

function fetch_rss_proxied(string $url): array {
    $api = 'https://api.rss2json.com/v1/api.json?rss_url=' . urlencode($url);
    $ch = curl_init($api);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 10,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_USERAGENT      => 'MorningDashboard/2.0',
        CURLOPT_SSL_VERIFYPEER => true,
    ]);
    $json = curl_exec($ch);
    curl_close($ch);
    if (!$json) return [['Could not load feed', '']];

    $data = json_decode($json, true);
    if (!isset($data['items'])) return [['No items found', '']];

    $items = [];
    foreach (array_slice($data['items'], 0, 10) as $item) {
        $title = strip_tags(trim($item['title'] ?? ''));
        $link  = $item['link'] ?? '';
        if ($title) $items[] = [$title, $link];
    }
    return $items ?: [['No items found', '']];
}

$result = [];
foreach ($SOURCES as $name => $source) {
    $result[$name] = $source['proxy']
        ? fetch_rss_proxied($source['url'])
        : fetch_rss($source['url']);
}

echo json_encode(['sources' => $result], JSON_UNESCAPED_UNICODE);
