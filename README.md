[![GitHub Release](https://img.shields.io/github/v/release/kimdre/ansible.hcloud-backup?logo=github&label=Galaxy%20version&link=https%3A%2F%2Fgithub.com%2Fkimdre%2Fansible.hcloud-backup%2Freleases)](https://galaxy.ansible.com/ui/standalone/roles/kimdre/hcloud-backup/)

# Ansible Role: kimdre.hcloud-backup

Ansible role to create and rotate backups and snapshots of servers in Hetzner Cloud.

<!-- TOC -->

* [Requirements](#requirements)
* [Role Variables](#role-variables)
    * [api_token](#api_token)
    * [id](#id)
* [Default Variables](#default-variables)
* [Example Playbook](#example-playbook)
* [Check Mode](#check-mode)
* [Development](#development)
* [License](#license)
* [Author](#author)

<!-- TOC -->

## Requirements

- Ansible core 2.15 or later, with a supported Python version.
- A Hetzner Cloud API token with read/write access.
- A Hetzner Cloud server ID in each target host's `id` variable.
- The delegated host must have Python installed and HTTPS access to `api.hetzner.cloud`.

## Role Variables

### api_token

Hetzner Cloud API token. Must be a nonempty string.

**Example**

```yaml
api_token: "your-hcloud-token"
```

Can also be set as the controller's environment variable `HCLOUD_TOKEN`.
An explicit `api_token` variable takes precedence.

### id

The target server's Hetzner Cloud ID, as a positive integer or decimal string.
The role uses this ID for image creation, checking whether backups are enabled, and snapshot ownership checks.
The inventory hostname does not need to match the server name.

Set `id` in host variables or use an inventory plugin that provides it, such as `hetzner.hcloud.hcloud`.

## Default Variables

See [defaults/main.yml](https://github.com/kimdre/ansible.hcloud-backup/blob/main/defaults/main.yml) for all available variables.

### backup_type

Type of backup to create.

#### Possible formats:

- `snapshot` is generally cheaper with smaller servers and disk usage and there is no limit on the number of snapshots
  that can be created.
- `backup` needs to be enabled first for the server and only 7 backups can be created per server before they get rotated.

The role does not stop servers or quiesce applications. Use application-specific backup or shutdown procedures
when your workload requires consistent database or filesystem state.

#### Default value

```yaml
backup_type: snapshot
```

### backup_description

Description of the snapshot/backup. Must be a string. Quotes, backslashes and newlines are JSON-escaped automatically.

#### Default value

```yaml
backup_description: "{{ inventory_hostname }} {{ now(fmt='%Y-%m-%d %H:%M:%S') }}"
```

### backup_labels

Dictionary of labels of the snapshot/backup. Keys and values must be strings that follow the
[Hetzner Cloud label rules](https://docs.hetzner.cloud/reference/cloud#labels):

- Key names and nonempty values have 63 characters or less. They start and end with a letter or digit.
  Between these, they can contain letters, digits, underscores, dots and hyphens.
- Keys can have an optional DNS subdomain prefix of 253 characters or less, followed by `/`,
  for example `example.com/rotation`. The `hetzner.cloud/` prefix is reserved.
- Values can be empty.

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

Dictionary of labels to identify snapshots for rotation.
When rotation is enabled, this dictionary must be nonempty and every key/value pair must match
[`backup_labels`](#backup_labels). Values cannot be empty, because the Hetzner Cloud API
does not document a selector for an empty label value.

Only used when [`backup_type`](#backup_type) is set to `snapshot` and [`rotate_snapshots`](#rotate_snapshots) is `true`.

#### Possible formats:

- `key: "value"`

#### Default value

```yaml
label_selector:
    created_by: ansible.hcloud-backup
    host: "{{ inventory_hostname }}"
    rotation: "true"
```

### rotate_snapshots

Rotate snapshots, if set to `true`, the oldest matching snapshots will be deleted
depending on the [`keep_snapshots`](#keep_snapshots) variable and the number of existing snapshots.
Must be a YAML boolean, not a quoted string.

Rotation runs only after image creation succeeds. The role reads all pages of available snapshots,
filters by the label selector and original server ID, and sorts by creation time before deletion.
Snapshots from other servers or without an original server ID are not deleted.
The newest matching snapshots are retained. Snapshots with different labels are not counted or deleted.

Only used when [`backup_type`](#backup_type) is set to `snapshot`.

#### Default value

```yaml
rotate_snapshots: true
```

### keep_snapshots

Number of matching snapshots to keep, as an integer between 1 and 40. Older snapshots will be deleted.

Only used when [`backup_type`](#backup_type) is set to `snapshot`
and [`rotate_snapshots`](#rotate_snapshots) is set to `true`.

#### Default value

```yaml
keep_snapshots: 5
```

### backup_check_retries

Number of retries for the backup creation check, as a nonnegative integer.
The role waits for the action status to become `success` and fails if it becomes `error`.
A value of `0` checks the action once without retrying.
The maximum wait time is about `backup_check_retries` x `backup_check_delay` seconds (30 minutes by default).
If the action is still running after the last check, the role fails and does not rotate snapshots.
Hetzner Cloud can still finish the image. Large disks can need more time.

#### Default value

```yaml
backup_check_retries: 120
```

### backup_check_delay

Delay in seconds between retries for the backup creation check, as a nonnegative integer.

#### Default value

```yaml
backup_check_delay: 15
```

### delegation

Host to run API requests from. Use `localhost` to run requests from the Ansible controller.
Input validation always runs on the controller.

#### Default value

```yaml
delegation: "{{ inventory_hostname }}"
```

## Example Playbook

Each host must provide its server ID. The following inventory uses `id: 12345` as a placeholder.

`inventory.yml`

```yaml
all:
  hosts:
    my-server:
      id: 12345
```

`backup.yml`

```yaml
- name: "Create snapshot of host"
  hosts: '{{ target | default("all") }}'
  gather_facts: false
  roles:
    - role: kimdre.hcloud-backup
      vars:
        delegation: localhost
        backup_type: "snapshot"
        keep_snapshots: 7
```

Set `HCLOUD_TOKEN` in the controller environment, then run the playbook with this inventory.
Do not store a real API token in the playbook.

## Check Mode

With `--check`, the role validates its input variables without calling the Hetzner API.
It does not create images, delete snapshots, or check whether server backups are enabled.

Normal execution always creates a new image. Creation and deletion tasks report changes.
API task output is hidden to protect the token; failures report the task and available error details with the token redacted.

## Development

Install `ansible-core` and `yamllint` in a Python environment supported by your Ansible version.
With `ansible-playbook` on `PATH`, run the following commands from the repository root.

```shell
yamllint .
python3 -m unittest discover -s tests -v
```

The tests run the role against a local mock HTTP API in a temporary directory.
They do not need credentials or access to Hetzner Cloud.
CI covers Ansible 2.15 with Python 3.11 and Ansible 2.20 with Python 3.12.
YAML lint rules are shared between local runs and CI through `.yamllint.yml`.

## License

Apache-2.0

## Author

- [Kim Oliver Drechsel](https://github.com/kimdre)
