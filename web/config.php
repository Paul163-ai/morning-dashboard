<?php
// Your login username — this account gets the admin panel
define('ADMIN_USER', 'paul');

// Absolute path to your .htpasswd file
// Find this in DirectAdmin → Password Protected Directories, or ask your host
define('HTPASSWD_FILE', '/home/paul163/domains/md.paullintott.uk/.htpasswd');

// Rate limiting uses REMOTE_ADDR (the true client IP on this DirectAdmin host).
// If a CDN or load balancer is ever added in front, revisit this — all clients
// would share one IP and the limit would either lock everyone out or be ineffective.
