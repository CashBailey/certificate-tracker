<?php
// Roundcube IMAP/SMTP connection configuration.
// All values are env-var-driven; defaults are safe for GreenMail dev server.
$config['imap_conn_options'] = [
    'ssl' => [
        'verify_peer'      => filter_var(getenv('ROUNDCUBE_IMAP_VERIFY_PEER') ?: 'false', FILTER_VALIDATE_BOOLEAN),
        'verify_peer_name' => filter_var(getenv('ROUNDCUBE_IMAP_VERIFY_PEER_NAME') ?: 'false', FILTER_VALIDATE_BOOLEAN),
    ],
];
$config['smtp_conn_options'] = [
    'ssl' => [
        'verify_peer'      => filter_var(getenv('ROUNDCUBE_SMTP_VERIFY_PEER') ?: 'false', FILTER_VALIDATE_BOOLEAN),
        'verify_peer_name' => filter_var(getenv('ROUNDCUBE_SMTP_VERIFY_PEER_NAME') ?: 'false', FILTER_VALIDATE_BOOLEAN),
    ],
];
$config['smtp_auth_type'] = getenv('ROUNDCUBE_SMTP_AUTH_TYPE') ?: '';
$config['smtp_user'] = getenv('ROUNDCUBE_SMTP_USER') ?: '';
$config['smtp_pass'] = getenv('ROUNDCUBE_SMTP_PASS') ?: '';

// City Directory plugin (global address book from PostgreSQL)
$config['plugins'] = array('city_directory');
$config['city_directory_dsn'] = getenv('CITY_DIRECTORY_DSN');
$config['city_directory_name'] = 'City Directory';

// Autocomplete searches City Directory first, then personal contacts
$config['autocomplete_addressbooks'] = array('city_directory', 'sql');
$config['autocomplete_single'] = true;

// Auto-collect recipients the user has emailed
$config['collected_recipients'] = true;
