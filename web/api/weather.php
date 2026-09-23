<?php
header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../helpers.php';

// Release the session lock before the slow upstream fetches below — see spurgeon.php.
session_write_close();

function curl_json(string $url): array {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 8,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_USERAGENT      => 'MorningDashboard/2.0',
        CURLOPT_SSL_VERIFYPEER => true,
    ]);
    $body = curl_exec($ch);
    curl_close($ch);
    if (!$body) throw new RuntimeException('No response');
    return json_decode($body, true) ?? [];
}

// Geocode search (for settings)
if (isset($_GET['geocode'])) {
    $q   = urlencode($_GET['geocode']);
    $res = curl_json("https://geocoding-api.open-meteo.com/v1/search?name={$q}&count=10&language=en&format=json");
    echo json_encode(['results' => $res['results'] ?? []], JSON_UNESCAPED_UNICODE);
    exit;
}

function weather_icon(int $code): string {
    $map = [
        0=>'☀️',1=>'🌤️',2=>'⛅',3=>'☁️',
        45=>'🌫️',48=>'🌫️',
        51=>'🌦️',53=>'🌦️',55=>'🌧️',
        61=>'🌧️',63=>'🌧️',65=>'🌧️',
        71=>'❄️',73=>'❄️',75=>'❄️',77=>'🌨️',
        80=>'🌦️',81=>'🌦️',82=>'🌧️',
        85=>'🌨️',86=>'🌨️',
        95=>'⛈️',96=>'⛈️',99=>'⛈️',
    ];
    return $map[$code] ?? '🌡️';
}

function weather_desc(int $code): string {
    $map = [
        0=>'Clear sky',1=>'Mainly clear',2=>'Partly cloudy',3=>'Overcast',
        45=>'Foggy',48=>'Icy fog',
        51=>'Light drizzle',53=>'Drizzle',55=>'Heavy drizzle',
        61=>'Light rain',63=>'Rain',65=>'Heavy rain',
        71=>'Light snow',73=>'Snow',75=>'Heavy snow',77=>'Snow grains',
        80=>'Showers',81=>'Showers',82=>'Heavy showers',
        85=>'Snow showers',86=>'Heavy snow showers',
        95=>'Thunderstorm',96=>'Thunderstorm',99=>'Thunderstorm',
    ];
    return $map[$code] ?? "Code $code";
}

function compass(float $deg): string {
    $dirs = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'];
    return $dirs[(int)round($deg / 22.5) % 16];
}

try {
    // Resolve coordinates
    if (!empty($_GET['lat']) && !empty($_GET['lon'])) {
        $lat  = (float)$_GET['lat'];
        $lon  = (float)$_GET['lon'];
        $city = $_GET['location'] ?? 'Your location';
    } elseif (!empty($_GET['location'])) {
        $q   = urlencode($_GET['location']);
        $geo = curl_json("https://geocoding-api.open-meteo.com/v1/search?name={$q}&count=1&language=en&format=json");
        $r   = $geo['results'][0] ?? null;
        if (!$r) throw new RuntimeException('Location not found: ' . $_GET['location']);
        $lat  = (float)$r['latitude'];
        $lon  = (float)$r['longitude'];
        $city = $r['name'] ?? $_GET['location'];
    } else {
        $loc  = curl_json('https://ipapi.co/json/');
        $lat  = (float)($loc['latitude']  ?? 51.5);
        $lon  = (float)($loc['longitude'] ?? -0.1);
        $city = $loc['city'] ?? 'Your location';
    }

    $w = curl_json(
        "https://api.open-meteo.com/v1/forecast"
        . "?latitude={$lat}&longitude={$lon}"
        . "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,"
        . "wind_speed_10m,wind_direction_10m,wind_gusts_10m,is_day"
        . "&hourly=temperature_2m,weather_code,precipitation_probability"
        . "&daily=weathercode,temperature_2m_max,temperature_2m_min,sunrise,sunset,"
        . "uv_index_max,precipitation_probability_max"
        . "&temperature_unit=celsius&wind_speed_unit=mph&timezone=auto"
    );

    $cur  = $w['current'] ?? [];
    $temp = (isset($cur['temperature_2m']) ? round($cur['temperature_2m']) : '--') . '°C';
    $code = (int)($cur['weather_code'] ?? 0);
    $desc = weather_desc($code) . '  —  ' . $city;
    $icon = weather_icon($code);

    $daily    = $w['daily'] ?? [];
    $dates    = $daily['time']                          ?? [];
    $codes    = $daily['weathercode']                   ?? [];
    $maxtemps = $daily['temperature_2m_max']             ?? [];
    $mintemps = $daily['temperature_2m_min']             ?? [];
    $sunrises = $daily['sunrise']                        ?? [];
    $sunsets  = $daily['sunset']                         ?? [];
    $uvmax    = $daily['uv_index_max']                   ?? [];
    $rainmax  = $daily['precipitation_probability_max']  ?? [];

    $forecast = [];
    for ($i = 0; $i < min(7, count($dates)); $i++) {
        $d    = new DateTime($dates[$i]);
        $forecast[] = [
            'day'  => $d->format('D'),
            'icon' => weather_icon((int)($codes[$i] ?? 0)),
            'hi'   => isset($maxtemps[$i]) ? round($maxtemps[$i]) . '°' : '--',
            'lo'   => isset($mintemps[$i]) ? round($mintemps[$i]) . '°' : '--',
        ];
    }

    $today = [
        'hi'          => isset($maxtemps[0]) ? round($maxtemps[0]) . '°' : '--',
        'lo'          => isset($mintemps[0]) ? round($mintemps[0]) . '°' : '--',
        'rain_chance' => isset($rainmax[0]) ? round($rainmax[0]) . '%' : '--',
        'uv_index'    => isset($uvmax[0]) ? round($uvmax[0], 1) : '--',
        'sunrise'     => isset($sunrises[0]) ? (new DateTime($sunrises[0]))->format('g:ia') : '--',
        'sunset'      => isset($sunsets[0])  ? (new DateTime($sunsets[0]))->format('g:ia')  : '--',
    ];

    $details = [
        'feels_like' => isset($cur['apparent_temperature']) ? round($cur['apparent_temperature']) . '°C' : '--',
        'humidity'   => isset($cur['relative_humidity_2m']) ? round($cur['relative_humidity_2m']) . '%' : '--',
        'wind'       => isset($cur['wind_speed_10m'])
            ? round($cur['wind_speed_10m']) . ' mph ' . compass((float)($cur['wind_direction_10m'] ?? 0))
            : '--',
        'wind_gusts' => isset($cur['wind_gusts_10m']) ? round($cur['wind_gusts_10m']) . ' mph' : '--',
    ];

    // Next 12 hours from now
    $hourly     = $w['hourly'] ?? [];
    $htimes     = $hourly['time']                      ?? [];
    $htemps     = $hourly['temperature_2m']             ?? [];
    $hcodes     = $hourly['weather_code']                ?? [];
    $hrain      = $hourly['precipitation_probability']   ?? [];
    $now        = new DateTime($w['current']['time'] ?? 'now');
    $startIdx   = 0;
    foreach ($htimes as $idx => $t) {
        if (new DateTime($t) >= $now) { $startIdx = $idx; break; }
    }
    $hourly_forecast = [];
    for ($i = $startIdx; $i < min($startIdx + 12, count($htimes)); $i++) {
        $t = new DateTime($htimes[$i]);
        $hourly_forecast[] = [
            'time'        => $t->format('ga'),
            'icon'        => weather_icon((int)($hcodes[$i] ?? 0)),
            'temp'        => isset($htemps[$i]) ? round($htemps[$i]) . '°' : '--',
            'rain_chance' => isset($hrain[$i]) ? round($hrain[$i]) . '%' : '--',
        ];
    }

    echo json_encode(compact('temp','icon','desc','forecast','today','details','hourly_forecast'), JSON_UNESCAPED_UNICODE);
} catch (Exception $e) {
    echo json_encode(['temp'=>'--°C','icon'=>'🌡️','desc'=>'Could not load weather: '.$e->getMessage(),'forecast'=>[],'today'=>[],'details'=>[],'hourly_forecast'=>[]]);
}
