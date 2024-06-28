# hcloud-backup

Ansible role to create and rotate backups and snapshots of servers in Hetzner Cloud.

## Requirements

- Ansible 2.15 or later

## Role Variables

### hcloud_token

Hetzner Cloud API token.

**Example**
```yaml
hcloud_token: "your-hcloud-token"
```

Can also be set as an environment variable `HCLOUD_TOKEN`.

## Default Variables

See [hcloud-backup/defaults/main.yml](hcloud-backup/defaults/main.yml) for all available variables.

### backup_type

Type of backup to create. Can be `snapshot` or `backup`.

- `snapshot` is generally cheaper with smaller servers and disk usage and there is no limit on the number of snapshots that can be created
- `backup` needs to be enabled first for the server and only 7 backups can be created per server

#### Default value

```yaml
backup_type: snapshot
```

### backup_description

Description of the snapshot/backup.

#### Default value

```yaml
backup_description: "{{ inventory_hostname }} {{ now(fmt='%Y-%m-%d-%H:%M:%S') }}"
```

### backup_labels

List of labels of the snapshot/backup.
Format: `key: "value"`

#### Default value

```yaml
backup_labels:
  created_by: "ansible.hcloud-backup"
  host: "{{ inventory_hostname }}"
  created_at: "{{ now(fmt='%Y-%m-%d_%H-%M-%S') }}"
```

### label_selector

Labels to identify a snapshots for rotation, should overlap with [`backup_labels`](#backup_labels).

Only used when [`backup_type`](#backup_type) is set to `snapshot`.

Format: `key=value` or `key`, separate multiple labels with a comma: `key1=value1,key2=value2`

#### Default value

```yaml
label_selector: "created_by=ansible.hcloud-backup,host={{ inventory_hostname }}"
```

### rotate_snapshots

Rotate snapshots, if set to `true`, the oldest snapshot(s) will be deleted based
depending on the [`keep_snapshots`](#keep_snapshots) variable.

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
- hosts: all
  roles:
    - role: hcloud-backup
      vars:
        hcloud_token: "your-hcloud-token"
        backup_type: "snapshot"
        backup_description: "Backup of {{ inventory_hostname }}"
        backup_labels:
          created_by: "ansible.hcloud-backup"
          host: "{{ inventory_hostname }}"
          created_at: "{{ now(fmt='%Y-%m-%d_%H-%M-%S') }}"
        label_selector: "created_by=ansible.hcloud-backup,host={{ inventory_hostname }}"
        rotate_snapshots: true
        keep_snapshots: 5
```

## Dependencies

- [hetzner.hcloud](https://galaxy.ansible.com/ui/repo/published/hetzner/hcloud/)

## License

Apache-2.0

## Author

- [Kim Oliver Drechsel](https://github.com/kimdre)
