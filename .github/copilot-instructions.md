# Repository instructions

## Project

This repository contains the `kimdre.hcloud-backup` Ansible role. It creates a Hetzner Cloud server backup or snapshot and optionally rotates snapshots.

The canonical repository URL is `https://github.com/kimdre/ansible.hcloud-backup`. Preserve it in documentation and badges.

## Layout

- `defaults/main.yml` defines role defaults and the API token lookup.
- `tasks/main.yml` validates inputs, creates the backup, and conditionally rotates snapshots.
- `tasks/validate.yml` contains input checks and the backup-enabled check.
- `tasks/backup.yml` creates the image and waits for the Hetzner action to finish.
- `tasks/rotate-snapshots.yml` finds matching snapshots and deletes those beyond the retention count.
- `meta/main.yml` defines Ansible Galaxy role metadata.
- `README.md` documents the role variables and playbook usage.

## Changes

- Keep task files focused on their existing role in the workflow.
- Validate user-provided values in `tasks/validate.yml` before using them in API requests.
- Use the existing `delegation` variable for tasks that call the Hetzner API.
- When changing role variables or defaults, update the README documentation as well.
- Keep YAML indentation at two spaces. The YAML lint workflow extends yamllint's default rules, sets the line-length threshold to 120 characters, and permits one space inside brackets.

## Validation

The GitHub Actions workflow at `.github/workflows/lint.yml` runs YAML lint and offline regression tests. Run `yamllint .` (it reads `.yamllint.yml` and skips paths in `.gitignore`) and `python3 -m unittest discover -s tests -v` with `ansible-playbook` on PATH. Tests copy the role into a temporary directory and replace only the API origin with a local mock server.
