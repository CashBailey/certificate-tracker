#!/usr/bin/env sh
# RH_MANAGED_FILE: repo-hygiene-autopilot v1
# Shared helpers for repo-hygiene scripts.
# shellcheck shell=sh

# `rh doctor` exit-code flags.
RH_RC_NOT_REPO=64
RH_RC_ON_DEFAULT=1
RH_RC_DIRTY=2
RH_RC_NO_UPSTREAM=4
RH_RC_DIVERGED=8
RH_RC_WORKTREE=16
RH_RC_DEFAULT_UNKNOWN=32

rh_log() {
  printf '%s\n' "$*"
}

rh_warn() {
  printf 'WARN: %s\n' "$*" >&2
}

rh_err() {
  printf 'ERROR: %s\n' "$*" >&2
}

rh_die() {
  rh_err "$*"
  exit 1
}

rh_init_defaults() {
  RH_PRIMARY_REMOTE=""
  RH_DEFAULT_BRANCH=""
  RH_USE_WORKTREES=1
  RH_WORKTREE_ROOT=".worktrees"
  RH_MAX_STAGED_FILE_BYTES=5242880
  RH_PRECOMMIT_CMD=""
  RH_PROTECTED_BRANCH_PATTERNS="main master develop release/* hotfix/*"
  RH_UNTRACKED_WARN_THRESHOLD=100
  RH_MAX_UNSTAGED_WARN=20
  RH_MAX_UNTRACKED_WARN=30
  RH_SPRAWL_RATIO_WARN=5
  RH_PRECOMMIT_SPRAWL_CHECK=1
}

rh_load_config() {
  rh_init_defaults

  default_conf="${1:-}"
  if [ -n "$default_conf" ] && [ -f "$default_conf" ]; then
    # shellcheck disable=SC1090
    . "$default_conf"
  fi

  if rh_require_git_repo; then
    repo_root=$(rh_repo_root)
    repo_conf="$repo_root/.repo-hygiene/config/rh.conf"
    if [ -f "$repo_conf" ]; then
      # shellcheck disable=SC1090
      . "$repo_conf"
    fi
  fi
}

rh_require_git_repo() {
  git rev-parse --is-inside-work-tree >/dev/null 2>&1
}

rh_repo_root() {
  git rev-parse --show-toplevel 2>/dev/null
}

rh_git_has_worktree() {
  git worktree list >/dev/null 2>&1
}

rh_current_branch() {
  git symbolic-ref --quiet --short HEAD 2>/dev/null || printf 'DETACHED'
}

rh_branch_exists() {
  git show-ref --verify --quiet "refs/heads/$1"
}

rh_remote_exists() {
  candidate="$1"
  [ -n "$candidate" ] || return 1
  git remote 2>/dev/null | grep -Fx "$candidate" >/dev/null 2>&1
}

rh_primary_remote() {
  if [ -n "${RH_PRIMARY_REMOTE:-}" ] && rh_remote_exists "$RH_PRIMARY_REMOTE"; then
    printf '%s\n' "$RH_PRIMARY_REMOTE"
    return 0
  fi

  if rh_remote_exists origin; then
    printf 'origin\n'
    return 0
  fi

  first_remote=$(git remote 2>/dev/null | sed -n '1p')
  if [ -n "$first_remote" ]; then
    printf '%s\n' "$first_remote"
    return 0
  fi

  return 1
}

rh_upstream_for_branch() {
  branch="$1"
  git rev-parse --abbrev-ref --symbolic-full-name "$branch@{upstream}" 2>/dev/null || true
}

rh_ahead_behind() {
  upstream="$1"
  branch="$2"

  counts=$(git rev-list --left-right --count "$upstream...$branch" 2>/dev/null || printf '0\t0')
  set -- $counts
  behind=${1:-0}
  ahead=${2:-0}
  printf '%s %s\n' "$behind" "$ahead"
}

rh_is_dirty() {
  [ -n "$(git status --porcelain=v1 2>/dev/null)" ]
}

rh_has_staged_changes() {
  [ -n "$(git diff --cached --name-only 2>/dev/null)" ]
}

rh_slugify() {
  if [ "$#" -eq 0 ]; then
    printf 'task-%s\n' "$(date +%Y%m%d-%H%M%S)"
    return
  fi

  raw="$*"
  slug=$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9][^a-z0-9]*/-/g; s/^-//; s/-$//')
  if [ -z "$slug" ]; then
    slug="task-$(date +%Y%m%d-%H%M%S)"
  fi
  printf '%s\n' "$slug"
}

rh_is_protected_branch() {
  branch="$1"
  for pattern in $RH_PROTECTED_BRANCH_PATTERNS; do
    case "$branch" in
      $pattern)
        return 0
        ;;
    esac
  done
  return 1
}

rh_detect_default_branch() {
  if [ -n "${RH_DEFAULT_BRANCH:-}" ]; then
    printf '%s\n' "$RH_DEFAULT_BRANCH"
    return 0
  fi

  remote=$(rh_primary_remote || true)
  if [ -n "$remote" ]; then
    remote_head=$(git symbolic-ref --quiet --short "refs/remotes/$remote/HEAD" 2>/dev/null || true)
    if [ -n "$remote_head" ]; then
      printf '%s\n' "${remote_head#${remote}/}"
      return 0
    fi

    remote_show_head=$(git remote show "$remote" 2>/dev/null | sed -n 's/^[[:space:]]*HEAD branch: //p' | sed -n '1p')
    if [ -n "$remote_show_head" ] && [ "$remote_show_head" != "(unknown)" ]; then
      printf '%s\n' "$remote_show_head"
      return 0
    fi
  fi

  init_default=$(git config --get init.defaultBranch 2>/dev/null || true)
  if [ -n "$init_default" ]; then
    printf '%s\n' "$init_default"
    return 0
  fi

  if rh_branch_exists main; then
    printf 'main\n'
    return 0
  fi

  if rh_branch_exists master; then
    printf 'master\n'
    return 0
  fi

  current_branch=$(rh_current_branch)
  if [ "$current_branch" != "DETACHED" ] && [ -n "$current_branch" ]; then
    printf '%s\n' "$current_branch"
    return 0
  fi

  return 1
}

rh_remote_default_branch() {
  remote="$1"
  remote_head=$(git symbolic-ref --quiet --short "refs/remotes/$remote/HEAD" 2>/dev/null || true)
  if [ -n "$remote_head" ]; then
    printf '%s\n' "${remote_head#${remote}/}"
    return 0
  fi

  fallback=$(rh_detect_default_branch || true)
  if [ -n "$fallback" ]; then
    printf '%s\n' "$fallback"
    return 0
  fi

  return 1
}

rh_find_worktree_for_branch() {
  target_branch="$1"
  current_worktree=""

  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      worktree\ *)
        current_worktree=${line#worktree }
        ;;
      branch\ refs/heads/*)
        listed_branch=${line#branch refs/heads/}
        if [ "$listed_branch" = "$target_branch" ]; then
          printf '%s\n' "$current_worktree"
          return 0
        fi
        ;;
    esac
  done <<__RH_WT_LIST__
$(git worktree list --porcelain 2>/dev/null || true)
__RH_WT_LIST__

  return 1
}

rh_worktree_issues() {
  current_worktree=""

  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      worktree\ *)
        current_worktree=${line#worktree }
        if [ ! -d "$current_worktree" ]; then
          printf 'MISSING|%s\n' "$current_worktree"
        fi
        ;;
      locked)
        printf 'LOCKED_NO_REASON|%s\n' "$current_worktree"
        ;;
      locked\ *)
        reason=${line#locked }
        printf 'LOCKED|%s|%s\n' "$current_worktree" "$reason"
        ;;
    esac
  done <<__RH_WT_ISSUES__
$(git worktree list --porcelain 2>/dev/null || true)
__RH_WT_ISSUES__
}

rh_worktree_count() {
  count=$(git worktree list --porcelain 2>/dev/null | grep -c '^worktree ' || true)
  printf '%s\n' "$count"
}

rh_local_merged_branches() {
  default_branch="$1"
  current_branch="$2"

  git for-each-ref --format='%(refname:short)' refs/heads --merged "$default_branch" | while IFS= read -r branch; do
    [ -n "$branch" ] || continue
    [ "$branch" = "$default_branch" ] && continue
    [ "$branch" = "$current_branch" ] && continue
    rh_is_protected_branch "$branch" && continue
    printf '%s\n' "$branch"
  done
}

rh_remote_merged_branches() {
  remote="$1"
  default_branch="$2"

  merged_ref="refs/remotes/$remote/$default_branch"
  git show-ref --verify --quiet "$merged_ref" || return 0

  git for-each-ref --format='%(refname:short)' "refs/remotes/$remote" --merged "$merged_ref" | while IFS= read -r refname; do
    [ -n "$refname" ] || continue
    branch_name=${refname#${remote}/}
    [ "$branch_name" = "HEAD" ] && continue
    [ "$branch_name" = "$default_branch" ] && continue
    rh_is_protected_branch "$branch_name" && continue
    printf '%s\n' "$branch_name"
  done
}

rh_untracked_count() {
  count=$(git status --porcelain=v1 2>/dev/null | grep -c '^?? ' || true)
  printf '%s\n' "$count"
}

rh_now_stamp() {
  date +%Y%m%d-%H%M%S
}
