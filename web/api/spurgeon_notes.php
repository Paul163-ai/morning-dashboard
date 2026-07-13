<?php
header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../helpers.php';

$notes_file = user_data_dir() . '/spurgeon_notes.json';

function load_notes(string $file): array {
    if (!file_exists($file)) return [];
    $data = json_decode(file_get_contents($file), true);
    return is_array($data) ? $data : [];
}

// Export all notes as plain text file
if (isset($_GET['export'])) {
    header('Content-Type: text/plain; charset=utf-8');
    header('Content-Disposition: attachment; filename="spurgeon_notes.txt"');
    $data = load_notes($notes_file);
    ksort($data);
    $lines = [];
    foreach ($data as $key => $text) {
        try {
            $d = new DateTime($key);
            $heading = $d->format('l, d F Y');
        } catch (Exception $e) {
            $heading = $key;
        }
        $lines[] = "── $heading ──";
        $lines[] = trim($text);
        $lines[] = '';
        $lines[] = '';
    }
    echo implode("\n", $lines);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $body = json_decode(file_get_contents('php://input'), true);

    if (isset($body['all']) && is_array($body['all'])) {
        $data = [];
        foreach ($body['all'] as $key => $text) {
            $date = preg_replace('/[^0-9\-]/', '', (string)$key);
            if ($date !== '' && $text !== '') {
                $data[$date] = $text;
            }
        }
        file_put_contents($notes_file, json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
        echo json_encode(['ok' => true]);
        exit;
    }

    $date = preg_replace('/[^0-9\-]/', '', $body['date'] ?? date('Y-m-d'));
    $text = $body['text'] ?? '';

    $data = load_notes($notes_file);
    if ($text !== '') {
        $data[$date] = $text;
    } else {
        unset($data[$date]);
    }
    file_put_contents($notes_file, json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
    echo json_encode(['ok' => true]);
} elseif (isset($_GET['all'])) {
    echo json_encode(['notes' => load_notes($notes_file)], JSON_UNESCAPED_UNICODE);
} else {
    $date = preg_replace('/[^0-9\-]/', '', $_GET['date'] ?? date('Y-m-d'));
    $data = load_notes($notes_file);
    echo json_encode(['text' => $data[$date] ?? '']);
}
