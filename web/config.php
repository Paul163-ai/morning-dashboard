<?php
// Your login username — this account gets the admin panel
define('ADMIN_USER', 'paul');

// Email address notified when someone submits an access request
define('ADMIN_EMAIL', 'paul.lintott@gmail.com');

// Public base URL, used to build links in emails (never derived from the
// request's Host header, which the client controls)
define('APP_URL', 'https://md.paullintott.uk');

// Absolute path to your .htpasswd file
// Find this in DirectAdmin → Password Protected Directories, or ask your host
define('HTPASSWD_FILE', '/home/paul163/domains/md.paullintott.uk/.htpasswd');

// Rate limiting uses REMOTE_ADDR (the true client IP on this DirectAdmin host).
// If a CDN or load balancer is ever added in front, revisit this — all clients
// would share one IP and the limit would either lock everyone out or be ineffective.
