<!-- RH_MANAGED_FILE: repo-hygiene-autopilot v1 -->
# Repo Hygiene

This repository uses `./.repo-hygiene/rh` to keep branches, worktrees, and remotes clean during AI-assisted coding.

## Invariants

- Never code directly on the default branch.
- Keep one task per branch.
- Prefer one worktree per active task.
- Never switch tasks with uncommitted changes unless you explicitly commit, stash, or discard.
- Never run destructive cleanup without a preview and explicit opt-in.
- Never force-push shared branches.

## Quickstart

```bash
chmod +x .repo-hygiene/rh .repo-hygiene/hooks/pre-commit .repo-hygiene/hooks/pre-push
cp -n .repo-hygiene/config/rh.conf.example .repo-hygiene/config/rh.conf
./.repo-hygiene/rh doctor
./.repo-hygiene/rh start "my task"
```

Optional hook install:

```bash
# If core.hooksPath is set, install there; otherwise installs to .git/hooks
hooks_path="$(git config --get core.hooksPath 2>/dev/null || true)"
if [ -z "$hooks_path" ]; then hooks_path=".git/hooks"; fi
mkdir -p "$hooks_path"
cp .repo-hygiene/hooks/pre-commit "$hooks_path/pre-commit"
cp .repo-hygiene/hooks/pre-push "$hooks_path/pre-push"
chmod +x "$hooks_path/pre-commit" "$hooks_path/pre-push"
```

## Main Commands

- `./.repo-hygiene/rh doctor`
- `./.repo-hygiene/rh start "<task>"`
- `./.repo-hygiene/rh precommit`
- `./.repo-hygiene/rh finish --mode pr`
- `./.repo-hygiene/rh cleanup --local --dry-run`
- `./.repo-hygiene/rh recover`

## Refusal Rules

Require explicit user confirmation before running:
- `git push --force` / `git push --force-with-lease`
- `git reset --hard`
- `git clean -fdx`
- deleting unmerged branches
- deleting remote branches
- removing worktrees that may still be in use

## Exit Code Bits (`rh doctor`)

- `1` on default branch
- `2` dirty working tree/index
- `4` no upstream tracking
- `8` diverged branch (or detached HEAD)
- `16` worktree consistency issue
- `32` default branch unknown
- `64` not inside a Git repo
