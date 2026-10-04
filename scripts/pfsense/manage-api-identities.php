<?php

require_once('/etc/inc/config.inc');
require_once('/etc/inc/auth.inc');

if (!defined('NABLA_IDENTITY_ACTION') || !defined('NABLA_IDENTITY_TARGET')) {
    fwrite(STDERR, "ERROR: invoke this helper through diagnose-recover.sh\n");
    exit(2);
}

$action = (string)NABLA_IDENTITY_ACTION;
$target = (string)NABLA_IDENTITY_TARGET;
$passwords = [
    'fastapi_posture' => defined('NABLA_POSTURE_PASSWORD_B64')
        ? (string)NABLA_POSTURE_PASSWORD_B64
        : '',
    'fastapi_security' => defined('NABLA_SECURITY_PASSWORD_B64')
        ? (string)NABLA_SECURITY_PASSWORD_B64
        : '',
];
$definitions = [
    'fastapi_posture' => [
        'short' => 'posture',
        'descr' => 'FastAPI pfSense posture observer',
        'base_privs' => [
            'api-v2-system-version-get',
            'api-v2-status-services-get',
            'api-v2-services-dns-resolver-settings-get',
            'api-v2-system-dns-get',
        ],
    ],
    'fastapi_security' => [
        'short' => 'security',
        'descr' => 'FastAPI pfSense security observer',
        'base_privs' => [
            'api-v2-diagnostics-table-get',
        ],
    ],
];

function nabla_normalized_privs(array $privs): array {
    $privs = array_values(array_unique(array_map('strval', $privs)));
    if (function_exists('sort_user_privs')) {
        return sort_user_privs($privs);
    }
    sort($privs);
    return $privs;
}

function nabla_find_user_index(string $name): ?int {
    foreach (config_get_path('system/user', []) as $idx => $user) {
        if (($user['name'] ?? '') === $name) {
            return (int)$idx;
        }
    }
    return null;
}

function nabla_restapi_config(): array {
    foreach (config_get_path('installedpackages/package', []) as $package) {
        if (($package['name'] ?? '') === 'RESTAPI') {
            $conf = $package['conf'] ?? [];
            return is_array($conf) ? $conf : [];
        }
    }
    return [];
}

function nabla_restapi_keys_for(string $username): array {
    $api = nabla_restapi_config();
    $keys = $api['keys']['key'] ?? [];
    if (!is_array($keys)) {
        return [];
    }
    return array_values(array_filter(
        $keys,
        static fn(array $key): bool =>
            (string)($key['username'] ?? '') === $username
    ));
}

function nabla_desired_privs(array $definition, string $mode): array {
    $privs = $definition['base_privs'];
    if ($mode === 'rotation') {
        $privs[] = 'api-v2-auth-key-post';
    } else {
        $privs[] = 'user-config-readonly';
    }
    return nabla_normalized_privs($privs);
}

function nabla_ensure_all_group_membership(int $uid): void {
    $groups = config_get_path('system/group', []);
    foreach ($groups as $idx => $group) {
        if (($group['name'] ?? '') !== 'all') {
            continue;
        }
        $members = $group['member'] ?? [];
        if (!is_array($members)) {
            $members = [];
        }
        $members = array_map('strval', $members);
        if (!in_array((string)$uid, $members, true)) {
            $members[] = (string)$uid;
            $group['member'] = $members;
            config_set_path("system/group/{$idx}", $group);
        }
        return;
    }
    throw new RuntimeException('pfSense all-users group was not found');
}

function nabla_create_service_user(
    string $name,
    array $definition,
    array $privs,
    string $passwordB64
): void {
    if ($passwordB64 === '') {
        throw new RuntimeException(
            "missing password file for absent service user {$name}"
        );
    }
    $password = base64_decode($passwordB64, true);
    if (!is_string($password) || $password === '') {
        throw new RuntimeException("invalid password material for {$name}");
    }
    $errors = validate_password($name, $password);
    if (!empty($errors)) {
        throw new RuntimeException(
            "password validation failed for {$name}: " . implode('; ', $errors)
        );
    }

    $uid = (int)config_get_path('system/nextuid', 2000);
    $userItemConfig = [
        'idx' => null,
        'item' => [
            'scope' => 'user',
            'name' => $name,
            'descr' => $definition['descr'],
            'expires' => '',
            'dashboardcolumns' => 2,
            'authorizedkeys' => '',
            'ipsecpsk' => '',
            'uid' => $uid,
            'priv' => $privs,
        ],
    ];
    local_user_set_password($userItemConfig, $password);
    $user = $userItemConfig['item'];

    config_set_path('system/nextuid', $uid + 1);
    config_set_path('system/user/', $user);
    nabla_ensure_all_group_membership($uid);

    $users = config_get_path('system/user', []);
    usort(
        $users,
        static fn(array $left, array $right): int =>
            strcmp(
                (string)($left['name'] ?? ''),
                (string)($right['name'] ?? '')
            )
    );
    config_set_path('system/user', $users);
    local_user_set($user);
    printf("identity_action user=%s action=created\n", $name);
}

function nabla_reconcile_service_user(
    string $name,
    array $definition,
    string $mode,
    string $passwordB64
): bool {
    $desired = nabla_desired_privs($definition, $mode);
    $idx = nabla_find_user_index($name);
    if ($idx === null) {
        nabla_create_service_user($name, $definition, $desired, $passwordB64);
        $idx = nabla_find_user_index($name);
        if ($idx === null) {
            throw new RuntimeException("created user {$name} cannot be reloaded");
        }
    }

    $user = config_get_path("system/user/{$idx}", []);
    if ((int)($user['uid'] ?? -1) === 0 || $name === 'admin') {
        throw new RuntimeException(
            "refusing to mutate privileged identity {$name}"
        );
    }

    $changed = false;
    if (($user['scope'] ?? '') !== 'user') {
        $user['scope'] = 'user';
        $changed = true;
    }
    if (($user['descr'] ?? '') !== $definition['descr']) {
        $user['descr'] = $definition['descr'];
        $changed = true;
    }
    if (isset($user['disabled'])) {
        unset($user['disabled']);
        $changed = true;
    }

    $current = nabla_normalized_privs(
        is_array($user['priv'] ?? null) ? $user['priv'] : []
    );
    if ($current !== $desired) {
        $user['priv'] = $desired;
        $changed = true;
    }

    if ($changed) {
        config_set_path("system/user/{$idx}", $user);
    }

    // Service users inherit no named-group privileges; "all" is implicit.
    $namedGroups = local_user_get_groups($user);
    if (!empty($namedGroups)) {
        local_user_set_groups($user, []);
        $changed = true;
    }
    nabla_ensure_all_group_membership((int)$user['uid']);
    local_user_set($user);

    printf(
        "identity_action user=%s action=%s mode=%s\n",
        $name,
        $changed ? 'reconciled' : 'unchanged',
        $mode
    );
    return $changed;
}

function nabla_report_identity(
    string $name,
    array $definition,
    string $expectedMode
): bool {
    $idx = nabla_find_user_index($name);
    if ($idx === null) {
        printf("identity user=%s exists=no state=missing\n", $name);
        return false;
    }

    $user = config_get_path("system/user/{$idx}", []);
    $privs = nabla_normalized_privs(
        is_array($user['priv'] ?? null) ? $user['priv'] : []
    );
    $desired = nabla_desired_privs($definition, $expectedMode);
    $missing = array_values(array_diff($desired, $privs));
    $unexpected = array_values(array_diff($privs, $desired));
    $namedGroups = local_user_get_groups($user);
    sort($namedGroups);
    $keys = nabla_restapi_keys_for($name);

    $ok = !isset($user['disabled'])
        && (($user['scope'] ?? '') === 'user')
        && empty($namedGroups)
        && empty($missing)
        && empty($unexpected);

    printf(
        "identity user=%s exists=yes enabled=%s scope=%s groups=%s mode=%s privileges=%s missing=%s unexpected=%s state=%s\n",
        $name,
        isset($user['disabled']) ? 'no' : 'yes',
        (string)($user['scope'] ?? '<unset>'),
        empty($namedGroups) ? '<none>' : implode(',', $namedGroups),
        $expectedMode,
        implode(',', $privs),
        empty($missing) ? '<none>' : implode(',', $missing),
        empty($unexpected) ? '<none>' : implode(',', $unexpected),
        $ok ? 'ok' : 'drift'
    );

    foreach ($keys as $key) {
        $descr = preg_replace('/\s+/', ' ', (string)($key['descr'] ?? ''));
        printf(
            "api_key user=%s length_bytes=%s hash_algo=%s descr=%s hash_present=%s\n",
            $name,
            (string)($key['length_bytes'] ?? 'unknown'),
            (string)($key['hash_algo'] ?? 'unknown'),
            $descr === '' ? '<empty>' : $descr,
            empty($key['hash']) ? 'no' : 'yes'
        );
    }
    printf("api_key_count user=%s count=%d\n", $name, count($keys));
    return $ok;
}

$selected = [];
foreach ($definitions as $name => $definition) {
    if ($target === 'all' || $definition['short'] === $target) {
        $selected[$name] = $definition;
    }
}
if (empty($selected)) {
    fwrite(STDERR, "ERROR: no service identity selected\n");
    exit(2);
}

$api = nabla_restapi_config();
$authMethods = $api['auth_methods'] ?? [];
if (!is_array($authMethods)) {
    $authMethods = [$authMethods];
}
sort($authMethods);
printf(
    "restapi enabled=%s login_protection=%s auth_methods=%s keyauth_enabled=%s\n",
    (string)($api['enabled'] ?? 'unknown'),
    (string)($api['login_protection'] ?? 'unknown'),
    implode(',', $authMethods),
    in_array('KeyAuth', $authMethods, true) ? 'yes' : 'no'
);

try {
    $changed = false;
    if ($action === 'apply') {
        // Validate all missing-user password inputs before making any mutation.
        foreach ($selected as $name => $definition) {
            if (
                nabla_find_user_index($name) === null
                && ($passwords[$name] ?? '') === ''
            ) {
                throw new RuntimeException(
                    "user {$name} is missing; provide its PFSENSE_*_PASSWORD_FILE"
                );
            }
        }
        foreach ($selected as $name => $definition) {
            $changed = nabla_reconcile_service_user(
                $name,
                $definition,
                'steady',
                $passwords[$name] ?? ''
            ) || $changed;
        }
    } elseif ($action === 'prepare') {
        foreach ($selected as $name => $definition) {
            if (nabla_find_user_index($name) === null) {
                throw new RuntimeException(
                    "user {$name} is missing; run --apply-identities first"
                );
            }
            $changed = nabla_reconcile_service_user(
                $name,
                $definition,
                'rotation',
                ''
            ) || $changed;
        }
    } elseif ($action === 'finalize') {
        foreach ($selected as $name => $definition) {
            if (nabla_find_user_index($name) === null) {
                throw new RuntimeException("user {$name} is missing");
            }
            if (count(nabla_restapi_keys_for($name)) < 1) {
                throw new RuntimeException(
                    "user {$name} has no persisted REST API key; refusing finalization"
                );
            }
            $changed = nabla_reconcile_service_user(
                $name,
                $definition,
                'steady',
                ''
            ) || $changed;
        }
    } elseif ($action !== 'check') {
        throw new RuntimeException("unsupported identity action {$action}");
    }

    if ($changed) {
        write_config(
            'Reconciled FastAPI pfSense REST API service identities'
        );
    }
} catch (Throwable $exc) {
    fwrite(STDERR, 'ERROR: ' . $exc->getMessage() . "\n");
    exit(3);
}

$expectedMode = $action === 'prepare' ? 'rotation' : 'steady';
$ok = true;
foreach ($selected as $name => $definition) {
    $ok = nabla_report_identity(
        $name,
        $definition,
        $expectedMode
    ) && $ok;
}

if ($action === 'check') {
    foreach ($selected as $name => $definition) {
        if (count(nabla_restapi_keys_for($name)) < 1) {
            fwrite(
                STDERR,
                "WARN: {$name} has no persisted REST API key; rights may be valid but KeyAuth cannot succeed\n"
            );
        }
    }
}

exit($ok ? 0 : 4);
