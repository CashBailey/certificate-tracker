<?php
/**
 * Read-only address book backend that queries certificates.employees
 * in PostgreSQL and injects certs@ci.laredo.tx.us as a pinned entry.
 */

class city_directory_backend extends rcube_addressbook
{
    public $primary_key = 'ID';
    public $readonly    = true;
    public $groups      = false;
    public $group_id    = null;

    private $dsn;
    private $name;
    private $pdo;
    private $filter     = '';
    private $result;
    protected $error;

    // Virtual ID for the pinned certs@ entry (won't collide with real IDs)
    const CERTS_VIRTUAL_ID = 'certs';
    const CERTS_EMAIL      = 'certs@ci.laredo.tx.us';
    const CERTS_DISPLAY    = 'Certificate Submissions';

    function __construct($dsn, $name)
    {
        $this->dsn  = $dsn;
        $this->name = $name;
    }

    function get_name()
    {
        return $this->name;
    }

    function set_search_set($filter)
    {
        $this->filter = $filter;
    }

    function get_search_set()
    {
        return $this->filter;
    }

    function reset()
    {
        $this->result = null;
        $this->filter = '';
    }

    function get_result()
    {
        return $this->result;
    }

    // ------------------------------------------------------------------ //
    //  PDO connection
    // ------------------------------------------------------------------ //

    private function db()
    {
        if ($this->pdo) {
            return $this->pdo;
        }

        // Parse DSN: pgsql://user:pass@host:port/dbname
        $parts = parse_url($this->dsn);
        $host  = $parts['host'] ?? 'postgres';
        $port  = $parts['port'] ?? 5432;
        $db    = ltrim($parts['path'] ?? '/laredo_certificates', '/');
        $user  = $parts['user'] ?? 'laredo';
        $pass  = $parts['pass'] ?? '';

        try {
            $this->pdo = new PDO(
                "pgsql:host={$host};port={$port};dbname={$db}",
                $user,
                $pass,
                [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]
            );
        } catch (PDOException $e) {
            rcube::raise_error([
                'code' => 500,
                'message' => "city_directory: DB connection failed - " . $e->getMessage(),
            ], true, false);
            $this->error = $e->getMessage();
        }

        return $this->pdo;
    }

    // ------------------------------------------------------------------ //
    //  Record helpers
    // ------------------------------------------------------------------ //

    private function make_record($row)
    {
        $name = trim($row['first_name'] . ' ' . $row['last_name']);
        return [
            'ID'        => $row['id'],
            'name'      => $name,
            'firstname' => $row['first_name'],
            'surname'   => $row['last_name'],
            'email'     => [$row['email']],
        ];
    }

    private function certs_record()
    {
        return [
            'ID'        => self::CERTS_VIRTUAL_ID,
            'name'      => self::CERTS_DISPLAY,
            'firstname' => 'Certificate',
            'surname'   => 'Submissions',
            'email'     => [self::CERTS_EMAIL],
        ];
    }

    // ------------------------------------------------------------------ //
    //  list_records
    // ------------------------------------------------------------------ //

    function list_records($cols = null, $subset = 0, $nocount = false)
    {
        $db = $this->db();
        $this->result = new rcube_result_set();

        if (!$db) {
            return $this->result;
        }

        try {
            $sql = "SELECT id, first_name, last_name, email
                    FROM certificates.employees
                    WHERE is_active = true AND role != 'Admin'
                    ORDER BY last_name, first_name";
            $stmt = $db->query($sql);
            $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
        } catch (PDOException $e) {
            rcube::raise_error([
                'code' => 500,
                'message' => "city_directory: query failed - " . $e->getMessage(),
            ], true, false);
            return $this->result;
        }

        // Pin certs@ as first entry
        $this->result->add($this->certs_record());

        foreach ($rows as $row) {
            $this->result->add($this->make_record($row));
        }

        $this->result->count = count($rows) + 1; // +1 for certs@

        return $this->result;
    }

    // ------------------------------------------------------------------ //
    //  search
    // ------------------------------------------------------------------ //

    function search($fields, $value, $mode = 0, $select = true, $nocount = false, $required = [])
    {
        $db = $this->db();
        $this->result = new rcube_result_set();

        if (!$db || empty($value)) {
            return $this->result;
        }

        // Normalize value to string
        if (is_array($value)) {
            $value = implode(' ', $value);
        }

        // Split into tokens for multi-word search (same logic as the API)
        $tokens = preg_split('/\s+/', trim($value));
        $tokens = array_filter($tokens);

        if (empty($tokens)) {
            return $this->result;
        }

        // Check if certs@ matches the search
        $certs_matches = true;
        foreach ($tokens as $t) {
            $tl = mb_strtolower($t);
            if (
                stripos(self::CERTS_DISPLAY, $t) === false &&
                stripos(self::CERTS_EMAIL, $t) === false
            ) {
                $certs_matches = false;
                break;
            }
        }

        try {
            // Build WHERE clause: each token must match at least one field
            $where_clauses = [];
            $params = [];
            $i = 0;
            foreach ($tokens as $token) {
                $param = "%{$token}%";
                $p1 = ":t{$i}a";
                $p2 = ":t{$i}b";
                $p3 = ":t{$i}c";
                $where_clauses[] = "(first_name ILIKE {$p1} OR last_name ILIKE {$p2} OR email ILIKE {$p3})";
                $params[$p1] = $param;
                $params[$p2] = $param;
                $params[$p3] = $param;
                $i++;
            }

            $sql = "SELECT id, first_name, last_name, email
                    FROM certificates.employees
                    WHERE is_active = true AND role != 'Admin'
                      AND " . implode(' AND ', $where_clauses) . "
                    ORDER BY last_name, first_name";

            $stmt = $db->prepare($sql);
            $stmt->execute($params);
            $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
        } catch (PDOException $e) {
            rcube::raise_error([
                'code' => 500,
                'message' => "city_directory: search failed - " . $e->getMessage(),
            ], true, false);
            return $this->result;
        }

        $count = count($rows);

        if ($certs_matches) {
            $this->result->add($this->certs_record());
            $count++;
        }

        foreach ($rows as $row) {
            $this->result->add($this->make_record($row));
        }

        $this->result->count = $count;

        return $this->result;
    }

    // ------------------------------------------------------------------ //
    //  count
    // ------------------------------------------------------------------ //

    function count()
    {
        $db = $this->db();

        if (!$db) {
            return new rcube_result_set(0);
        }

        try {
            $sql = "SELECT COUNT(*) FROM certificates.employees WHERE is_active = true AND role != 'Admin'";
            $stmt = $db->query($sql);
            $total = (int) $stmt->fetchColumn() + 1; // +1 for certs@
        } catch (PDOException $e) {
            $total = 0;
        }

        return new rcube_result_set($total);
    }

    // ------------------------------------------------------------------ //
    //  get_record
    // ------------------------------------------------------------------ //

    function get_record($id, $assoc = false)
    {
        $this->result = new rcube_result_set(1);

        if ($id === self::CERTS_VIRTUAL_ID) {
            $this->result->add($this->certs_record());
            return $assoc ? $this->certs_record() : $this->result;
        }

        $db = $this->db();
        if (!$db) {
            return $assoc ? [] : $this->result;
        }

        try {
            $stmt = $db->prepare(
                "SELECT id, first_name, last_name, email
                 FROM certificates.employees WHERE id = :id"
            );
            $stmt->execute([':id' => (int) $id]);
            $row = $stmt->fetch(PDO::FETCH_ASSOC);
        } catch (PDOException $e) {
            return $assoc ? [] : $this->result;
        }

        if ($row) {
            $rec = $this->make_record($row);
            $this->result->add($rec);
            return $assoc ? $rec : $this->result;
        }

        return $assoc ? [] : $this->result;
    }

    // ------------------------------------------------------------------ //
    //  Stubs for read-only address book
    // ------------------------------------------------------------------ //

    function create_group($name) { return false; }
    function delete_group($gid) { return false; }
    function rename_group($gid, $newname, &$newid) { return $newname; }
    function add_to_group($gid, $ids) { return 0; }
    function remove_from_group($gid, $ids) { return 0; }
}
