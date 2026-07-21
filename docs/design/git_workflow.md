# Git branch and worktree workflow

## Long-lived branches

- `main`: stable release history. Do not develop directly in its worktree.
- `develop`: integration branch for completed, reviewed work.

Levels are scopes, not permanent divergent branches. Mark stable milestones with annotated tags such as `level-01-v0.7.0`. Long-lived `level/01`, `level/02`, and similar branches are intentionally avoided because shared schemas, orchestration, validation, and reporting would drift and create unnecessary conflicts.

## Short-lived branch names

- `feature/level-01/<task>`: Level 1 behavior.
- `experiment/level-01/<algorithm>`: research algorithms or experiment infrastructure.
- `feature/shared/<task>`: shared code used by multiple levels.
- `feature/level-02/<task>`: only after Level 2 is explicitly activated.
- `fix/level-01/<issue>`: corrective Level 1 work.
- `docs/<topic>`: documentation-only changes.

Create each branch from the latest local `develop`, merge it back after tests and independent validation, then remove its worktree and branch. Never attach the same branch to two worktrees.

## Local worktree layout

Worktrees live outside the repository directory:

```text
D:/IT/Project/gsm/
├── 3DBinPacking/                  # develop integration worktree
└── 3DBinPacking-worktrees/
    ├── main/                      # clean main/release worktree
    ├── level-01-<task>/           # one short-lived Level 1 branch
    ├── shared-<task>/             # one shared feature branch
    └── level-02-<task>/           # created only when Level 2 is active
```

Each worktree uses its own ignored `.venv`. Sharing one editable virtual environment across worktrees is prohibited because its package path can point at the wrong source tree. Generated outputs stay inside that worktree's ignored `outputs/` hierarchy.

## Example task lifecycle

```powershell
git -C D:\IT\Project\gsm\3DBinPacking switch develop
git -C D:\IT\Project\gsm\3DBinPacking pull --ff-only  # only when remote synchronization is authorized
git -C D:\IT\Project\gsm\3DBinPacking branch experiment/level-01/tabu-search
git -C D:\IT\Project\gsm\3DBinPacking worktree add `
  D:\IT\Project\gsm\3DBinPacking-worktrees\level-01-tabu-search `
  experiment/level-01/tabu-search
```

After implementation:

```powershell
python -m pytest -q
git status --short
git add <explicit paths>
git commit
git -C D:\IT\Project\gsm\3DBinPacking switch develop
git -C D:\IT\Project\gsm\3DBinPacking merge --no-ff experiment/level-01/tabu-search
git -C D:\IT\Project\gsm\3DBinPacking worktree remove `
  D:\IT\Project\gsm\3DBinPacking-worktrees\level-01-tabu-search
git -C D:\IT\Project\gsm\3DBinPacking branch -d experiment/level-01/tabu-search
git worktree prune
```

Do not run `pull`, `push`, merge into `main`, delete a worktree with uncommitted changes, or force-delete a branch without explicit authorization and a clean-state check.

## Integration checks

Before merging a task into `develop`:

1. confirm the feature worktree is clean after its commit;
2. run targeted tests and the full test suite;
3. run the relevant end-to-end experiment and independent validator;
4. inspect `git diff develop...<feature-branch>`;
5. use `git merge-tree` or a no-commit merge to inspect conflicts;
6. merge into `develop`, rerun the full suite, and only then remove the task worktree.

Before promoting `develop` to `main`, perform the same checks from the clean `main` worktree and create a release tag only after the merge commit is verified.
