# RH_MANAGED_FILE: repo-hygiene-autopilot v1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DefaultConfigPath = Join-Path $ScriptDir 'config/rh.conf'

$RC_NOT_REPO = 64
$RC_ON_DEFAULT = 1
$RC_DIRTY = 2
$RC_NO_UPSTREAM = 4
$RC_DIVERGED = 8
$RC_WORKTREE = 16
$RC_DEFAULT_UNKNOWN = 32

$script:RhConfig = @{}

function Write-Info {
  param([string]$Message)
  Write-Host $Message
}

function Fail {
  param(
    [string]$Message,
    [int]$Code = 1
  )
  Write-Error $Message
  exit $Code
}

function Test-GitRepo {
  & git rev-parse --is-inside-work-tree *> $null
  return ($LASTEXITCODE -eq 0)
}

function Get-RepoRoot {
  $out = (& git rev-parse --show-toplevel 2>$null)
  if ($LASTEXITCODE -ne 0) { return '' }
  return ($out | Select-Object -First 1).Trim()
}

function Get-CurrentBranch {
  $out = (& git symbolic-ref --quiet --short HEAD 2>$null)
  if ($LASTEXITCODE -ne 0) { return 'DETACHED' }
  return ($out | Select-Object -First 1).Trim()
}

function Test-Dirty {
  $out = (& git status --porcelain=v1 2>$null)
  return [bool]($out -and $out.Count -gt 0)
}

function Get-Remotes {
  $out = (& git remote 2>$null)
  if ($LASTEXITCODE -ne 0) { return @() }
  return @($out | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Test-BranchExists {
  param([string]$Branch)
  & git show-ref --verify --quiet ("refs/heads/$Branch") *> $null
  return ($LASTEXITCODE -eq 0)
}

function Get-Upstream {
  param([string]$Branch)
  $out = (& git rev-parse --abbrev-ref --symbolic-full-name "${Branch}@{upstream}" 2>$null)
  if ($LASTEXITCODE -ne 0) { return '' }
  return ($out | Select-Object -First 1).Trim()
}

function Get-AheadBehind {
  param(
    [string]$Upstream,
    [string]$Branch
  )
  $out = (& git rev-list --left-right --count "$Upstream...$Branch" 2>$null)
  if ($LASTEXITCODE -ne 0 -or -not $out) {
    return @{ Behind = 0; Ahead = 0 }
  }

  $parts = (($out | Select-Object -First 1) -split "\s+")
  if ($parts.Count -lt 2) {
    return @{ Behind = 0; Ahead = 0 }
  }

  return @{ Behind = [int]$parts[0]; Ahead = [int]$parts[1] }
}

function Parse-ConfigFile {
  param([string]$Path)

  if (-not (Test-Path $Path)) { return }

  $lines = Get-Content -LiteralPath $Path
  foreach ($line in $lines) {
    if ($line -match '^\s*$') { continue }
    if ($line -match '^\s*#') { continue }
    if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { continue }

    $key = $Matches[1]
    $value = $Matches[2].Trim()

    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
      $value = $value.Substring(1, $value.Length - 2)
    }

    $script:RhConfig[$key] = $value
  }
}

function Load-Config {
  $script:RhConfig = @{
    RH_PRIMARY_REMOTE = ''
    RH_DEFAULT_BRANCH = ''
    RH_USE_WORKTREES = '1'
    RH_WORKTREE_ROOT = '.worktrees'
    RH_MAX_STAGED_FILE_BYTES = '5242880'
    RH_PRECOMMIT_CMD = ''
    RH_PROTECTED_BRANCH_PATTERNS = 'main master develop release/* hotfix/*'
    RH_UNTRACKED_WARN_THRESHOLD = '100'
  }

  $configPath = if ($env:RH_CONFIG_PATH) { $env:RH_CONFIG_PATH } else { $DefaultConfigPath }
  Parse-ConfigFile -Path $configPath

  if (Test-GitRepo) {
    $repoRoot = Get-RepoRoot
    if ($repoRoot) {
      $repoConfig = Join-Path $repoRoot '.repo-hygiene/config/rh.conf'
      Parse-ConfigFile -Path $repoConfig
    }
  }
}

function Get-PrimaryRemote {
  $configured = $script:RhConfig['RH_PRIMARY_REMOTE']
  $remotes = Get-Remotes

  if ($configured -and ($remotes -contains $configured)) {
    return $configured
  }

  if ($remotes -contains 'origin') {
    return 'origin'
  }

  if ($remotes.Count -gt 0) {
    return $remotes[0]
  }

  return ''
}

function Get-DefaultBranch {
  $configured = $script:RhConfig['RH_DEFAULT_BRANCH']
  if ($configured) { return $configured }

  $remote = Get-PrimaryRemote
  if ($remote) {
    $headRef = (& git symbolic-ref --quiet --short "refs/remotes/$remote/HEAD" 2>$null)
    if ($LASTEXITCODE -eq 0 -and $headRef) {
      $head = ($headRef | Select-Object -First 1).Trim()
      if ($head.StartsWith("$remote/")) {
        return $head.Substring($remote.Length + 1)
      }
    }

    $remoteShow = (& git remote show $remote 2>$null)
    if ($LASTEXITCODE -eq 0 -and $remoteShow) {
      $line = $remoteShow | Where-Object { $_ -match '^\s*HEAD branch:\s+' } | Select-Object -First 1
      if ($line) {
        $candidate = ($line -replace '^\s*HEAD branch:\s+', '').Trim()
        if ($candidate -and $candidate -ne '(unknown)') {
          return $candidate
        }
      }
    }
  }

  $initDefault = (& git config --get init.defaultBranch 2>$null)
  if ($LASTEXITCODE -eq 0 -and $initDefault) {
    return ($initDefault | Select-Object -First 1).Trim()
  }

  if (Test-BranchExists -Branch 'main') { return 'main' }
  if (Test-BranchExists -Branch 'master') { return 'master' }

  $current = Get-CurrentBranch
  if ($current -and $current -ne 'DETACHED') { return $current }

  return ''
}

function Get-RemoteDefaultBranch {
  param([string]$Remote)

  $headRef = (& git symbolic-ref --quiet --short "refs/remotes/$Remote/HEAD" 2>$null)
  if ($LASTEXITCODE -eq 0 -and $headRef) {
    $head = ($headRef | Select-Object -First 1).Trim()
    if ($head.StartsWith("$Remote/")) {
      return $head.Substring($Remote.Length + 1)
    }
  }

  return (Get-DefaultBranch)
}

function Get-Slug {
  param([string]$Text)

  $slug = $Text.ToLowerInvariant()
  $slug = [regex]::Replace($slug, '[^a-z0-9]+', '-')
  $slug = $slug.Trim('-')
  if (-not $slug) {
    return "task-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
  }
  return $slug
}

function Test-ProtectedBranch {
  param([string]$Branch)

  $patterns = $script:RhConfig['RH_PROTECTED_BRANCH_PATTERNS'] -split '\s+' | Where-Object { $_ }
  foreach ($pattern in $patterns) {
    if ($Branch -like $pattern) { return $true }
  }

  return $false
}

function Get-WorktreeEntries {
  $out = (& git worktree list --porcelain 2>$null)
  if ($LASTEXITCODE -ne 0 -or -not $out) { return @() }

  $entries = @()
  $current = $null

  foreach ($line in $out) {
    if ($line -match '^worktree\s+(.+)$') {
      if ($current) { $entries += [pscustomobject]$current }
      $current = [ordered]@{
        Path = $Matches[1]
        Branch = ''
        Locked = $false
        LockReason = ''
      }
      continue
    }

    if (-not $current) { continue }

    if ($line -match '^branch\s+refs/heads/(.+)$') {
      $current['Branch'] = $Matches[1]
      continue
    }

    if ($line -eq 'locked') {
      $current['Locked'] = $true
      $current['LockReason'] = ''
      continue
    }

    if ($line -match '^locked\s+(.+)$') {
      $current['Locked'] = $true
      $current['LockReason'] = $Matches[1]
      continue
    }
  }

  if ($current) { $entries += [pscustomobject]$current }
  return $entries
}

function Get-LocalMergedBranches {
  param(
    [string]$DefaultBranch,
    [string]$CurrentBranch
  )

  $out = (& git for-each-ref --format='%(refname:short)' refs/heads --merged $DefaultBranch 2>$null)
  if ($LASTEXITCODE -ne 0 -or -not $out) { return @() }

  $branches = @()
  foreach ($branch in $out) {
    $b = $branch.Trim()
    if (-not $b) { continue }
    if ($b -eq $DefaultBranch -or $b -eq $CurrentBranch) { continue }
    if (Test-ProtectedBranch -Branch $b) { continue }
    $branches += $b
  }

  return $branches
}

function Get-RemoteMergedBranches {
  param(
    [string]$Remote,
    [string]$DefaultBranch
  )

  & git show-ref --verify --quiet ("refs/remotes/$Remote/$DefaultBranch") *> $null
  if ($LASTEXITCODE -ne 0) { return @() }

  $out = (& git for-each-ref --format='%(refname:short)' "refs/remotes/$Remote" --merged "refs/remotes/$Remote/$DefaultBranch" 2>$null)
  if ($LASTEXITCODE -ne 0 -or -not $out) { return @() }

  $branches = @()
  foreach ($ref in $out) {
    $r = $ref.Trim()
    if (-not $r) { continue }
    if (-not $r.StartsWith("$Remote/")) { continue }

    $branch = $r.Substring($Remote.Length + 1)
    if ($branch -eq 'HEAD' -or $branch -eq $DefaultBranch) { continue }
    if (Test-ProtectedBranch -Branch $branch) { continue }

    $branches += $branch
  }

  return $branches
}

function Get-UntrackedCount {
  $status = (& git status --porcelain=v1 2>$null)
  if ($LASTEXITCODE -ne 0 -or -not $status) { return 0 }
  return (@($status | Where-Object { $_ -like '?? *' })).Count
}

function Invoke-Git {
  param(
    [string[]]$Args,
    [string]$ErrorMessage = 'Git command failed'
  )

  & git @Args
  if ($LASTEXITCODE -ne 0) {
    Fail "$ErrorMessage: git $($Args -join ' ')"
  }
}

function Show-Usage {
  Write-Info @"
Repo Hygiene (PowerShell)

Usage:
  rh.ps1 doctor
  rh.ps1 start <task> [--stash] [--worktree|--no-worktree]
  rh.ps1 precommit
  rh.ps1 finish [--mode merge|pr|wip|stash] [--yes]
  rh.ps1 cleanup [--local] [--remote] [--merged-only] [--dry-run] [--no-dry-run] [--yes]
  rh.ps1 recover
"@
}

function Invoke-Doctor {
  if (-not (Test-GitRepo)) {
    Write-Error 'Not inside a Git repository.'
    Write-Info "DOCTOR_EXIT_CODE=$RC_NOT_REPO"
    exit $RC_NOT_REPO
  }

  $rc = 0
  $repoRoot = Get-RepoRoot
  $defaultBranch = Get-DefaultBranch
  $currentBranch = Get-CurrentBranch
  $primaryRemote = Get-PrimaryRemote

  Write-Info "Repo root: $repoRoot"
  if ($primaryRemote) {
    Write-Info "Primary remote: $primaryRemote"
  }
  else {
    Write-Warning 'No remote configured.'
  }

  if ($defaultBranch) {
    Write-Info "Default branch: $defaultBranch"
  }
  else {
    Write-Warning 'Could not detect default branch.'
    $rc = $rc -bor $RC_DEFAULT_UNKNOWN
  }

  Write-Info "Current branch: $currentBranch"
  if ($currentBranch -eq 'DETACHED') {
    Write-Warning 'HEAD is detached.'
    $rc = $rc -bor $RC_DIVERGED
  }
  elseif ($defaultBranch -and $currentBranch -eq $defaultBranch) {
    Write-Warning "Current branch is default branch '$defaultBranch'."
    $rc = $rc -bor $RC_ON_DEFAULT
  }

  if (Test-Dirty) {
    Write-Warning 'Working tree/index is dirty.'
    $rc = $rc -bor $RC_DIRTY
  }
  else {
    Write-Info 'Working tree/index: clean'
  }

  if ($currentBranch -ne 'DETACHED') {
    $upstream = Get-Upstream -Branch $currentBranch
    if (-not $upstream) {
      Write-Warning "No upstream tracking branch for '$currentBranch'."
      $rc = $rc -bor $RC_NO_UPSTREAM
    }
    else {
      $ab = Get-AheadBehind -Upstream $upstream -Branch $currentBranch
      Write-Info "Upstream: $upstream (ahead=$($ab.Ahead) behind=$($ab.Behind))"
      if ($ab.Ahead -gt 0 -and $ab.Behind -gt 0) {
        Write-Warning 'Branch and upstream are diverged.'
        $rc = $rc -bor $RC_DIVERGED
      }
    }
  }

  $entries = Get-WorktreeEntries
  $missing = 0
  $locked = 0
  $lockedNoReason = 0

  foreach ($entry in $entries) {
    if (-not (Test-Path -LiteralPath $entry.Path)) {
      Write-Warning "Missing worktree directory: $($entry.Path)"
      $missing = 1
    }

    if ($entry.Locked) {
      $locked++
      if (-not $entry.LockReason) {
        Write-Warning "Locked worktree without reason: $($entry.Path)"
        $lockedNoReason = 1
      }
    }
  }

  Write-Info "Worktrees: total=$($entries.Count) locked=$locked missing_dirs=$missing"
  if ($missing -eq 1 -or $lockedNoReason -eq 1) {
    $rc = $rc -bor $RC_WORKTREE
  }

  if ($defaultBranch -and (Test-BranchExists -Branch $defaultBranch)) {
    $mergedLocal = Get-LocalMergedBranches -DefaultBranch $defaultBranch -CurrentBranch $currentBranch
    if ($mergedLocal.Count -gt 0) {
      Write-Info "Local branches merged into $defaultBranch:"
      $mergedLocal | ForEach-Object { Write-Info "  - $_" }
    }
    else {
      Write-Info "Local branches merged into $defaultBranch: none"
    }
  }
  else {
    Write-Warning 'Skipped local merged-branch report (default branch ref unavailable).'
  }

  $remotes = Get-Remotes
  if ($remotes.Count -eq 0) {
    Write-Info 'Remote branches merged into default branches: no remotes configured'
  }
  else {
    $printed = $false
    foreach ($remote in $remotes) {
      $remoteDefault = Get-RemoteDefaultBranch -Remote $remote
      if (-not $remoteDefault) { continue }
      $merged = Get-RemoteMergedBranches -Remote $remote -DefaultBranch $remoteDefault
      if ($merged.Count -gt 0) {
        $printed = $true
        Write-Info "Remote branches merged into $remote/$remoteDefault:"
        $merged | ForEach-Object { Write-Info "  - $remote/$_" }
      }
    }

    if (-not $printed) {
      Write-Info 'Remote branches merged into default branches: none'
    }
  }

  Write-Info "DOCTOR_EXIT_CODE=$rc"
  exit $rc
}

function Invoke-Start {
  param([string[]]$Args)

  $autoStash = $false
  $useWorktree = ($script:RhConfig['RH_USE_WORKTREES'] -eq '1')
  $taskParts = @()

  for ($i = 0; $i -lt $Args.Count; $i++) {
    $arg = $Args[$i]
    switch ($arg) {
      '--stash' { $autoStash = $true; continue }
      '--worktree' { $useWorktree = $true; continue }
      '--no-worktree' { $useWorktree = $false; continue }
      default {
        if ($arg.StartsWith('--')) {
          Fail "Unknown argument for start: $arg"
        }
        $taskParts += $arg
      }
    }
  }

  if ($taskParts.Count -eq 0) {
    Fail 'Usage: rh.ps1 start <task> [--stash] [--worktree|--no-worktree]'
  }

  if (-not (Test-GitRepo)) {
    Fail 'Not inside a Git repository.'
  }

  $task = ($taskParts -join ' ')
  if (Test-Dirty) {
    if ($autoStash) {
      $label = "rh:start:$(Get-Slug -Text $task):$(Get-Date -Format 'yyyyMMdd-HHmmss')"
      Invoke-Git -Args @('stash', 'push', '-u', '-m', $label) -ErrorMessage 'Failed to stash dirty workspace'
      Write-Info "Stashed uncommitted changes: $label"
    }
    else {
      Fail 'Working tree is dirty; commit, stash, or discard explicitly before starting a task.' 2
    }
  }

  $defaultBranch = Get-DefaultBranch
  if (-not $defaultBranch) {
    Fail 'Unable to detect default branch. Set RH_DEFAULT_BRANCH in .repo-hygiene/config/rh.conf'
  }

  $primaryRemote = Get-PrimaryRemote
  $baseRef = $defaultBranch
  if (-not (Test-BranchExists -Branch $defaultBranch)) {
    if ($primaryRemote) {
      & git show-ref --verify --quiet "refs/remotes/$primaryRemote/$defaultBranch" *> $null
      if ($LASTEXITCODE -eq 0) {
        $baseRef = "refs/remotes/$primaryRemote/$defaultBranch"
      }
      else {
        $baseRef = Get-CurrentBranch
      }
    }
    else {
      $baseRef = Get-CurrentBranch
    }
  }

  $slug = Get-Slug -Text $task
  $branch = "task/$slug"

  if ($useWorktree) {
    & git worktree list *> $null
    if ($LASTEXITCODE -ne 0) {
      $useWorktree = $false
    }
  }

  if ($useWorktree) {
    $existing = (Get-WorktreeEntries | Where-Object { $_.Branch -eq $branch } | Select-Object -First 1)
    if ($existing) {
      Write-Info "Branch already has a worktree: $($existing.Path)"
      Write-Info "Next: cd $($existing.Path)"
      return
    }

    $repoRoot = Get-RepoRoot
    $wtRoot = Join-Path $repoRoot $script:RhConfig['RH_WORKTREE_ROOT']
    $wtPath = Join-Path $wtRoot $slug

    if (-not (Test-Path -LiteralPath $wtRoot)) {
      New-Item -ItemType Directory -Path $wtRoot | Out-Null
    }

    if (Test-Path -LiteralPath $wtPath) {
      & git -C $wtPath rev-parse --is-inside-work-tree *> $null
      if ($LASTEXITCODE -eq 0) {
        Write-Info "Worktree already exists: $wtPath"
        Write-Info "Next: cd $wtPath"
        return
      }
      Fail "Target path exists and is not a git worktree: $wtPath"
    }

    if (Test-BranchExists -Branch $branch) {
      Invoke-Git -Args @('worktree', 'add', $wtPath, $branch) -ErrorMessage 'Failed to add worktree'
    }
    else {
      Invoke-Git -Args @('worktree', 'add', '-b', $branch, $wtPath, $baseRef) -ErrorMessage 'Failed to create branch worktree'
    }

    Write-Info "Created isolated worktree: $wtPath"
    Write-Info "Next: cd $wtPath"
  }
  else {
    if (Test-BranchExists -Branch $branch) {
      Invoke-Git -Args @('switch', $branch) -ErrorMessage 'Failed to switch branch'
      Write-Info "Switched to existing branch: $branch"
    }
    else {
      Invoke-Git -Args @('switch', '-c', $branch, $baseRef) -ErrorMessage 'Failed to create branch'
      Write-Info "Created and switched to branch: $branch"
    }
  }

  if ($primaryRemote) {
    Write-Info "Optional upstream setup: git push -u $primaryRemote $branch"
  }
}

function Invoke-Precommit {
  if (-not (Test-GitRepo)) {
    Fail 'Not inside a Git repository.'
  }

  $defaultBranch = Get-DefaultBranch
  $currentBranch = Get-CurrentBranch
  if ($defaultBranch -and $currentBranch -eq $defaultBranch) {
    Fail "Commit blocked: current branch '$currentBranch' is the default branch." 11
  }

  $staged = (& git diff --cached --name-only 2>$null)
  if ($LASTEXITCODE -ne 0 -or -not $staged) {
    Fail 'No staged changes. Stage files before committing.' 12
  }

  $maxBytes = 5242880
  [void][int]::TryParse($script:RhConfig['RH_MAX_STAGED_FILE_BYTES'], [ref]$maxBytes)

  $hugeFound = $false
  $conflictFound = $false

  foreach ($file in $staged) {
    $sizeOut = (& git cat-file -s ":$file" 2>$null)
    $size = 0
    if ($sizeOut) {
      [void][int]::TryParse(($sizeOut | Select-Object -First 1).Trim(), [ref]$size)
    }

    if ($size -gt $maxBytes) {
      Write-Error "Staged file exceeds $maxBytes bytes: $file ($size bytes)"
      $hugeFound = $true
    }

    $blob = (& git show ":$file" 2>$null)
    if ($blob -and ($blob | Select-String -Pattern '^(<<<<<<<|=======|>>>>>>>)' -SimpleMatch:$false)) {
      Write-Error "Merge conflict marker found in staged file: $file"
      $conflictFound = $true
    }
  }

  if ($hugeFound -or $conflictFound) {
    exit 13
  }

  $precommitCmd = $script:RhConfig['RH_PRECOMMIT_CMD']
  if ($precommitCmd) {
    Write-Info "Running configured precommit command: $precommitCmd"
    try {
      Invoke-Expression $precommitCmd
      if ($LASTEXITCODE -ne 0) {
        Fail 'Configured precommit command failed.' 14
      }
    }
    catch {
      Fail "Configured precommit command failed: $($_.Exception.Message)" 14
    }
  }

  Write-Info 'Precommit checks passed.'
}

function Invoke-Finish {
  param([string[]]$Args)

  $mode = 'pr'
  $yes = $false

  for ($i = 0; $i -lt $Args.Count; $i++) {
    $arg = $Args[$i]
    switch -Regex ($arg) {
      '^--mode=(.+)$' {
        $mode = $Matches[1]
        continue
      }
      '^--mode$' {
        if ($i + 1 -ge $Args.Count) { Fail 'Missing value for --mode' }
        $mode = $Args[$i + 1]
        $i++
        continue
      }
      '^--yes$' {
        $yes = $true
        continue
      }
      default {
        Fail "Unknown argument for finish: $arg"
      }
    }
  }

  if (-not (Test-GitRepo)) {
    Fail 'Not inside a Git repository.'
  }

  $defaultBranch = Get-DefaultBranch
  $currentBranch = Get-CurrentBranch
  $primaryRemote = Get-PrimaryRemote

  if ($currentBranch -eq 'DETACHED') {
    Fail "Detached HEAD. Run 'rh.ps1 recover' first." 21
  }

  if ($defaultBranch -and $currentBranch -eq $defaultBranch) {
    Fail "Finish blocked: you are on default branch '$defaultBranch'." 22
  }

  if (Test-Dirty) {
    switch ($mode) {
      'wip' {
        Invoke-Git -Args @('add', '-A') -ErrorMessage 'Failed to stage changes for WIP commit'
        & git diff --cached --quiet --ignore-submodules -- *> $null
        if ($LASTEXITCODE -eq 0) {
          Fail 'No committable changes after staging.' 23
        }
        Invoke-Git -Args @('commit', '-m', "wip($currentBranch): checkpoint $(Get-Date -Format 'yyyyMMdd-HHmmss')") -ErrorMessage 'Failed to create WIP commit'
        Write-Info 'Created WIP commit.'
      }
      'stash' {
        $label = "rh:finish:$currentBranch:$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        Invoke-Git -Args @('stash', 'push', '-u', '-m', $label) -ErrorMessage 'Failed to stash dirty workspace'
        Write-Info "Stashed uncommitted changes: $label"
      }
      default {
        Fail 'Working tree is dirty. Use --mode wip or --mode stash explicitly.' 24
      }
    }
  }

  if ($defaultBranch -and (Test-BranchExists -Branch $defaultBranch)) {
    $aheadOut = (& git rev-list --count "$defaultBranch..$currentBranch" 2>$null)
    $ahead = 0
    if ($aheadOut) { [void][int]::TryParse(($aheadOut | Select-Object -First 1).Trim(), [ref]$ahead) }
    if ($ahead -eq 0) {
      Write-Warning "Branch '$currentBranch' has no commits ahead of '$defaultBranch'."
    }
    else {
      Write-Info "Commits ahead of $defaultBranch: $ahead"
    }
  }

  $upstream = Get-Upstream -Branch $currentBranch
  if (-not $upstream -and $primaryRemote) {
    Write-Info "Upstream not set. Next: git push -u $primaryRemote $currentBranch"
  }

  switch ($mode) {
    'pr' {
      Write-Info 'Finish mode: pr'
      if ($primaryRemote) {
        Write-Info "Next: git push -u $primaryRemote $currentBranch"
      }
      Write-Info "Next: open a PR from '$currentBranch' to '${defaultBranch}'"
    }
    'wip' {
      Write-Info 'Finish mode: wip'
      if ($primaryRemote) {
        Write-Info "Next: git push -u $primaryRemote $currentBranch"
      }
    }
    'stash' {
      Write-Info 'Finish mode: stash'
      Write-Info 'Next: git stash list'
      Write-Info 'Next: git stash pop   # when resuming'
    }
    'merge' {
      if (-not $defaultBranch) {
        Fail 'Cannot merge: default branch is unknown.' 25
      }

      Write-Info 'Finish mode: merge requested'
      Write-Info "Rollback suggestion before merge: git tag rh/merge-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss') HEAD"

      if (-not $yes) {
        Write-Warning 'Merge preview only. Re-run with --yes to execute.'
        Write-Info "Preview commands:"
        Write-Info "  git switch $defaultBranch"
        Write-Info "  git merge --no-ff $currentBranch"
        if ($primaryRemote) {
          Write-Info "  git push $primaryRemote $defaultBranch"
        }
        exit 26
      }

      if (Test-Dirty) {
        Fail 'Cannot merge with a dirty working tree.' 27
      }

      Invoke-Git -Args @('switch', $defaultBranch) -ErrorMessage 'Failed to switch to default branch'
      Invoke-Git -Args @('merge', '--no-ff', $currentBranch) -ErrorMessage 'Failed to merge branch'
      Write-Info "Merged '$currentBranch' into '$defaultBranch' locally."
      if ($primaryRemote) {
        Write-Info "Next: git push $primaryRemote $defaultBranch"
      }
    }
    default {
      Fail "Unsupported finish mode: $mode"
    }
  }
}

function Invoke-Cleanup {
  param([string[]]$Args)

  $doLocal = $true
  $doRemote = $false
  $dryRun = $true
  $yes = $false

  foreach ($arg in $Args) {
    switch ($arg) {
      '--local' { $doLocal = $true; continue }
      '--remote' { $doRemote = $true; continue }
      '--merged-only' { continue }
      '--dry-run' { $dryRun = $true; continue }
      '--no-dry-run' { $dryRun = $false; continue }
      '--yes' { $yes = $true; $dryRun = $false; continue }
      default { Fail "Unknown argument for cleanup: $arg" }
    }
  }

  if (-not (Test-GitRepo)) {
    Fail 'Not inside a Git repository.'
  }

  if (-not $dryRun -and -not $yes) {
    Fail 'Refusing to execute cleanup without --yes. Use --dry-run to preview.'
  }

  if (-not $dryRun) {
    Write-Info "Rollback suggestion before cleanup: git tag rh/cleanup-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss') HEAD"
  }

  $defaultBranch = Get-DefaultBranch
  $currentBranch = Get-CurrentBranch
  Write-Info "Cleanup mode: $(if ($dryRun) { 'DRY-RUN' } else { 'EXECUTE' })"

  if ($doLocal) {
    if ($defaultBranch -and (Test-BranchExists -Branch $defaultBranch)) {
      $localCandidates = Get-LocalMergedBranches -DefaultBranch $defaultBranch -CurrentBranch $currentBranch
      if ($localCandidates.Count -eq 0) {
        Write-Info 'Local merged branches to clean: none'
      }
      else {
        Write-Info 'Local merged branches to clean:'
        foreach ($branch in $localCandidates) {
          if ($dryRun) {
            Write-Info "  - $branch (would run: git branch -d $branch)"
          }
          else {
            Write-Info "  - deleting local branch: $branch"
            Invoke-Git -Args @('branch', '-d', $branch) -ErrorMessage 'Failed to delete local branch'
          }
        }
      }
    }
    else {
      Write-Warning 'Skipping local cleanup: default branch unavailable locally.'
    }
  }

  if ($doRemote) {
    $remotes = Get-Remotes
    if ($remotes.Count -eq 0) {
      Write-Warning 'Skipping remote cleanup: no remotes configured.'
    }
    else {
      foreach ($remote in $remotes) {
        $remoteDefault = Get-RemoteDefaultBranch -Remote $remote
        if (-not $remoteDefault) {
          Write-Warning "Skipping remote '$remote': default branch unknown."
          continue
        }

        $remoteCandidates = Get-RemoteMergedBranches -Remote $remote -DefaultBranch $remoteDefault
        if ($remoteCandidates.Count -eq 0) {
          Write-Info "Remote merged branches to clean for $remote/$remoteDefault: none"
        }
        else {
          Write-Info "Remote merged branches to clean for $remote/$remoteDefault:"
          foreach ($branch in $remoteCandidates) {
            if ($dryRun) {
              Write-Info "  - $remote/$branch (would run: git push $remote --delete $branch)"
            }
            else {
              Write-Info "  - deleting remote branch: $remote/$branch"
              Invoke-Git -Args @('push', $remote, '--delete', $branch) -ErrorMessage 'Failed to delete remote branch'
            }
          }
        }

        if ($dryRun) {
          Write-Info "  - remote prune preview for $remote:"
          & git remote prune $remote --dry-run
        }
        else {
          Write-Info "  - pruning stale remote refs for $remote"
          Invoke-Git -Args @('remote', 'prune', $remote) -ErrorMessage 'Failed to prune remote refs'
        }
      }
    }
  }

  $entries = Get-WorktreeEntries
  $missing = @($entries | Where-Object { -not (Test-Path -LiteralPath $_.Path) })
  if ($missing.Count -gt 0) {
    foreach ($entry in $missing) {
      Write-Warning "Missing worktree metadata entry: $($entry.Path)"
    }

    if ($dryRun) {
      Write-Info 'Worktree metadata prune preview: git worktree prune --verbose --dry-run'
      & git worktree prune --verbose --dry-run
    }
    else {
      Write-Info 'Pruning stale worktree metadata'
      Invoke-Git -Args @('worktree', 'prune', '--verbose') -ErrorMessage 'Failed to prune worktree metadata'
    }
  }
  else {
    Write-Info 'Worktree metadata cleanup: no missing worktrees detected'
  }
}

function Invoke-Recover {
  if (-not (Test-GitRepo)) {
    Fail 'Not inside a Git repository.'
  }

  $defaultBranch = Get-DefaultBranch
  $currentBranch = Get-CurrentBranch
  $primaryRemote = Get-PrimaryRemote
  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

  Write-Info 'Step 1: Inspect current state'
  Write-Info '  git status -sb'
  Write-Info '  git branch --show-current'
  Write-Info '  git worktree list --porcelain'

  Write-Info 'Step 2: Backup before risky actions'
  Write-Info "  git tag rh/recover-$stamp HEAD"
  Write-Info "  git stash push -u -m 'rh:recover-$stamp'"

  Write-Info 'Detected state summary:'
  Write-Info "  - current branch: $currentBranch"
  Write-Info "  - default branch: $(if ($defaultBranch) { $defaultBranch } else { 'unknown' })"
  Write-Info "  - primary remote: $(if ($primaryRemote) { $primaryRemote } else { 'none' })"

  if ($currentBranch -eq 'DETACHED') {
    Write-Warning 'Detached HEAD detected.'
    Write-Info "Suggested safe path: git switch -c task/recovered-$stamp"
  }

  if ($defaultBranch -and $currentBranch -eq $defaultBranch -and (Test-Dirty)) {
    Write-Warning "Uncommitted edits detected on default branch '$defaultBranch'."
    Write-Info "Suggested safe path:"
    Write-Info "  git switch -c task/salvage-$stamp"
    Write-Info "  git add -A && git commit -m 'salvage: move work off $defaultBranch'"
  }

  $entries = Get-WorktreeEntries
  foreach ($entry in $entries) {
    if (-not (Test-Path -LiteralPath $entry.Path)) {
      Write-Warning "Lost worktree directory detected: $($entry.Path)"
      Write-Info 'Suggested safe path:'
      Write-Info '  git worktree prune --verbose --dry-run'
      Write-Info '  git worktree prune --verbose   # after review'
    }
  }

  if ($currentBranch -ne 'DETACHED') {
    $upstream = Get-Upstream -Branch $currentBranch
    if ($upstream) {
      $ab = Get-AheadBehind -Upstream $upstream -Branch $currentBranch
      if ($ab.Ahead -gt 0 -and $ab.Behind -gt 0) {
        Write-Warning "Diverged branch detected: $currentBranch vs $upstream"
        Write-Info 'Suggested safe path:'
        if ($primaryRemote) {
          Write-Info "  git fetch $primaryRemote"
        }
        Write-Info "  git log --oneline --left-right $upstream...$currentBranch"
        Write-Info "  git rebase $upstream   # rewrites history, confirm with team first"
        Write-Info '  # or: git merge {upstream}'
      }
    }
  }

  $threshold = 100
  [void][int]::TryParse($script:RhConfig['RH_UNTRACKED_WARN_THRESHOLD'], [ref]$threshold)
  $untracked = Get-UntrackedCount
  if ($untracked -ge $threshold) {
    Write-Warning "High untracked-file count detected: $untracked"
    Write-Info 'Suggested safe path:'
    Write-Info '  git clean -ndx   # preview only'
    Write-Info '  git clean -fdx   # destructive, run only with explicit approval'
  }

  Write-Info "No destructive action was executed by 'rh.ps1 recover'."
}

Load-Config

if ($args.Count -eq 0) {
  Show-Usage
  exit 0
}

$cmd = $args[0]
$rest = @()
if ($args.Count -gt 1) {
  $rest = $args[1..($args.Count - 1)]
}

switch ($cmd) {
  'doctor' { Invoke-Doctor }
  'start' { Invoke-Start -Args $rest }
  'precommit' { Invoke-Precommit }
  'finish' { Invoke-Finish -Args $rest }
  'cleanup' { Invoke-Cleanup -Args $rest }
  'recover' { Invoke-Recover }
  'help' { Show-Usage }
  '-h' { Show-Usage }
  '--help' { Show-Usage }
  default { Fail "Unknown command: $cmd" }
}
