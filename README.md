![Release version](https://img.shields.io/github/v/release/kimdre/ansible.hcloud-backup) (https://github.com/kimdre/ansible.hcloud-backup/releases)
[![Publish Ansible role to Galaxy](https://github.com/kimdre/ansible.hcloud-backup/actions/workflows/release.yml/badge.svg)](https://github.com/kimdre/ansible.hcloud-backup/actions/workflows/release.yml)

# Asible Role: kimdre.hcloud-backup

Ansible role to create and rotate backups and snapshots of servers in Hetzner Cloud.

<!-- TOC -->

* [Requirements](#requirements)
* [Role Variables](#role-variables)
    * [api_token](#api_token)
* [Default Variables](#default-variables)
* [Example Playbook](#example-playbook)
* [Dependencies](#dependencies)
* [License](#license)
* [Author](#author)

<!-- TOC -->

## Requirements

- Ansible 2.15 or later

## Role Variables

### api_token

Hetzner Cloud API token.

**Example**

```yaml
api_token: "your-hcloud-token"
```

Can also be set as an environment variable `HCLOUD_TOKEN`

## Default Variables

See [hcloud-backup/defaults/main.yml](https://github.com/kimdre/ansible.hcloud-backup/blob/main/defaults/main.yml) for
all available variables.

### backup_type

Type of backup to create.

#### Possible formats:

- `snapshot` is generally cheaper with smaller servers and disk usage and there is no limit on the number of snapshots
  that can be created.
- `backup` needs to be enabled first for the server and only 7 backups can be created per server before they get rotated.

#### Default value

```yaml
backup_type: snapshot
```

### backup_description

Description of the snapshot/backup.

#### Default value

```yaml
backup_description: "{{ inventory_hostname }} {{ now(fmt='%Y-%m-%d %H:%M:%S') }}"
```

### backup_labels

List of labels of the snapshot/backup.

#### Possible formats:

- `key: "value"`
- `key: ""`  for labels without a value.

#### Default value

```yaml
backup_labels:
    created_by: "ansible.hcloud-backup"
    created_at: "{{ now(fmt='%Y-%m-%d_%H-%M-%S') }}"
    host: "{{ inventory_hostname }}"
    rotation: "true"
```

### label_selector

List of labels to identify snapshots for rotation, should overlap with [`backup_labels`](#backup_labels).

Only used when [`backup_type`](#backup_type) is set to `snapshot`.

#### Possible formats:

- `key: "value"`
- `key: ""`  for labels without a value.

#### Default value

```yaml
label_selector:
    created_by: ansible.hcloud-backup
    host: "{{ inventory_hostname }}"
    rotation: "true"
```

### rotate_snapshots

Rotate snapshots, if set to `true`, the oldest found snapshot(s) will be deleted
depending on the [`keep_snapshots`](#keep_snapshots) variable and the number of existing snapshots.

Only used when [`backup_type`](#backup_type) is set to `snapshot`.

#### Default value

```yaml
rotate_snapshots: true
```

### keep_snapshots

Number of snapshots to keep, older snapshots will be deleted.

Only used when [`backup_type`](#backup_type) is set to `snapshot`
and [`rotate_snapshots`](#rotate_snapshots) is set to `true`.

#### Default value

```yaml
keep_snapshots: 5
```

### backup_check_retries

Number of retries for the backup creation check.

#### Default value

```yaml
backup_check_retries: 40
```

### backup_check_delay

Delay in seconds between retries for the backup creation check.

#### Default value

```yaml
backup_check_delay: 15
```

### delegation

Host to run the role tasks from

#### Default value

```yaml
delegation: "{{ inventory_hostname }}"
```

## Example Playbook

```yaml
- name: "Create snapshot of host"
  hosts: '{{ target | default("all") }}'
  roles:
    - role: kimdre.hcloud-backup
      vars:
        api_token: "your-hcloud-api-token"
        backup_type: "snapshot"
        keep_snapshots: 7
```

## Dependencies

- [hetzner.hcloud](https://galaxy.ansible.com/ui/repo/published/hetzner/hcloud/)

## License

Apache-2.0

## Author

- [Kim Oliver Drechsel](https://github.com/kimdre)
