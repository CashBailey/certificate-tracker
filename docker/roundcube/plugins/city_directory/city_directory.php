<?php
/**
 * City Directory - Roundcube global address book plugin.
 *
 * Provides a read-only address book backed by the City of Laredo
 * PostgreSQL employee database. All active employees appear in the
 * directory, with certs@ci.laredo.tx.us pinned as the first entry.
 *
 * Config keys (set in custom.inc.php):
 *   city_directory_dsn  - PDO DSN for PostgreSQL
 *   city_directory_name - Display name (default: "City Directory")
 */

class city_directory extends rcube_plugin
{
    function init()
    {
        $this->add_hook('addressbooks_list', [$this, 'address_sources']);
        $this->add_hook('addressbook_get',   [$this, 'get_address_book']);
    }

    function address_sources($p)
    {
        $rc = rcmail::get_instance();
        $p['sources']['city_directory'] = [
            'id'       => 'city_directory',
            'name'     => $rc->config->get('city_directory_name', 'City Directory'),
            'readonly' => true,
            'groups'   => false,
        ];
        return $p;
    }

    function get_address_book($p)
    {
        if ($p['id'] === 'city_directory') {
            $rc  = rcmail::get_instance();
            $dsn = $rc->config->get('city_directory_dsn', '');
            $name = $rc->config->get('city_directory_name', 'City Directory');
            require_once __DIR__ . '/city_directory_backend.php';
            $p['instance'] = new city_directory_backend($dsn, $name);
        }
        return $p;
    }
}
