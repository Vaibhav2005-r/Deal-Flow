#!/usr/bin/env bash
# name=cleanup_repo.sh
# Purpose: Mirror-backup + remove trailers and sensitive specs from history.
# Usage:
#   ./cleanup_repo.sh [--repo <ssh-or-https-repo-url>] [--backup-dir <dir>] [--push] [--yes]
# Example:
#   ./cleanup_claude.sh --repo https://github.com/Vaibhav2005-r/DealFlow_Odoo.git --push
set -euo pipefail

# Ensure virtualenv bin is in PATH for git-filter-repo
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -d "${SCRIPT_DIR}/.venv/bin" ]]; then
  export PATH="${SCRIPT_DIR}/.venv/bin:${PATH}"
fi

REPO_URL="https://github.com/Vaibhav2005-r/DealFlow_Odoo.git"
BACKUP_BASE="dealflow_backup_$(date +%Y%m%d_%H%M%S)"
MIRROR_DIR="${BACKUP_BASE}.git"
DO_PUSH=0
YES=0

usage() {
  cat <<EOF
Usage: $0 [--repo <repo_url>] [--backup-dir <dir>] [--push] [--yes]
  --repo       SSH/HTTPS URL of the repo (default: ${REPO_URL})
  --backup-dir Directory name for the mirror backup (default: ${MIRROR_DIR})
  --push       If provided, the script will push the rewritten history back to the remote (force). Otherwise it stops after verification.
  --yes        If provided together with --push, skips the interactive confirmation before pushing.
EOF
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO_URL="$2"; shift 2;;
    --backup-dir) MIRROR_DIR="$2"; shift 2;;
    --push) DO_PUSH=1; shift;;
    --yes) YES=1; shift;;
    -h|--help) usage;;
    *) echo "Unknown arg: $1"; usage;;
  esac
done

echo "Repository: $REPO_URL"
echo "Mirror backup dir: $MIRROR_DIR"
echo

# Prechecks
command -v git >/dev/null 2>&1 || { echo "git not found. Install git and retry."; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "python3 not found. Install python3 and retry."; exit 2; }

if ! python3 -c "import git_filter_repo" >/dev/null 2>&1; then
  echo "git-filter-repo python module not available."
  echo "Install it (recommended):"
  echo "  pip3 install git-filter-repo"
  echo "or follow: https://github.com/newren/git-filter-repo"
  echo
  # also check if git-filter-repo executable exists
  if ! command -v git-filter-repo >/dev/null 2>&1; then
    echo "Either install pip package or make git-filter-repo available on PATH, then retry."
    exit 3
  fi
fi

# 1) Create a mirror backup
if [[ -d "$MIRROR_DIR" ]]; then
  echo "Error: directory '$MIRROR_DIR' already exists. Please remove or choose a different --backup-dir."
  exit 4
fi

echo "Cloning mirror (this creates a full backup) ..."
git clone --mirror "$REPO_URL" "$MIRROR_DIR"
echo "Mirror clone complete: $MIRROR_DIR"
echo "Create an archive copy of the mirror for extra safety..."
tar -cJf "${MIRROR_DIR}.tar.xz" "$MIRROR_DIR"
echo "Archive saved to ${MIRROR_DIR}.tar.xz"
echo

cd "$MIRROR_DIR"

# 2) Prepare replace-text file to strip Co-Authored-By trailers
cat > remove_trailers.txt <<'EOF'
# Remove any Co-Authored-By trailers from commit messages (regex mode).
# Format: regex:<pattern>==><replacement>
# Replacement is empty (i.e., remove matching lines).
regex:(?m)^[ \t]*Co-Authored-By:.*$\n?==>
EOF

# 3) Prepare paths file listing files/folders to remove from history entirely
cat > paths-to-remove.txt <<'EOF'
CLAUDE.md
.claude/
EOF

echo "Prepared remove_trailers.txt and paths-to-remove.txt"

# 4) Run git-filter-repo
echo
echo "About to run git filter-repo to:"
echo "  - remove Co-Authored-By lines from commit messages"
echo "  - remove files/paths listed in paths-to-remove.txt from all history"
echo
echo "This will rewrite all refs in the mirror repo. The mirror is at: $(pwd)"
echo

# Run filter-repo
git-filter-repo --replace-message remove_trailers.txt --message-callback 'return re.sub(br"(?mi)^[ \t]*Co-Authored-By:.*$\n?", b"", message)' --invert-paths --paths-from-file paths-to-remove.txt

echo
echo "git-filter-repo finished."
echo

# 5) Verification checks
echo "Verification checks (searching rewritten history)..."
echo "Searching for any remaining 'Co-Authored-By' in commit messages:"
if git log --all --grep="Co-Authored-By" -i --oneline | sed -n '1,20p' | grep -q .; then
  git log --all --grep="Co-Authored-By" -i --oneline | sed -n '1,20p'
  echo "Warning: Found remaining Co-Authored-By lines above. Inspect before pushing."
else
  echo "No Co-Authored-By found in commit messages (good)."
fi
echo

echo "Checking for CLAUDE.md in objects/rev-list:"
if git rev-list --all --objects | grep -F "CLAUDE.md" >/dev/null 2>&1; then
  echo "Warning: CLAUDE.md still present in history (unexpected)."
else
  echo "CLAUDE.md not found in history (removed)."
fi
echo

# List refs summary
echo "Refs (heads and tags) present after rewrite:"
git for-each-ref --format='%(refname:short)' refs/heads refs/tags | sed -n '1,200p'
echo

# 6) Push instructions or push
if [[ "$DO_PUSH" -eq 1 ]]; then
  echo "You requested pushing the rewritten history back to origin. THIS IS DESTRUCTIVE and will force-update the remote."
  if [[ "$YES" -ne 1 ]]; then
    read -p "Type 'I UNDERSTAND' to continue with the forced push: " CONFIRM
    if [[ "$CONFIRM" != "I UNDERSTAND" ]]; then
      echo "Push aborted. Run the push command manually after verifying."
      echo "Push commands are printed below."
      DO_PUSH=0
    fi
  fi
fi

if [[ "$DO_PUSH" -eq 1 ]]; then
  echo "Pushing rewritten history to remote (force)."
  echo "If branch protections are enabled, this will fail until protections are temporarily disabled."
  # Use --mirror to ensure refs/tags are mirrored exactly (including deletions)
  git remote add origin "$REPO_URL" 2>/dev/null || git remote set-url origin "$REPO_URL"
  git push --force --mirror origin
  echo "Push complete."
  echo "Allow a few minutes for GitHub to recalculate contributors and other graphs."
else
  echo "Script completed locally. No push performed."
  echo "To push the rewritten history to the remote (destructive), run these commands from inside $MIRROR_DIR:"
  echo
  echo "  # double-check remote URL first"
  echo "  git remote add origin ${REPO_URL} 2>/dev/null || git remote set-url origin ${REPO_URL}"
  echo "  # push everything (force, mirror)"
  echo "  git push --force --mirror origin"
  echo
  echo "Or run this script again with --push (and --yes to skip prompt):"
  echo "  ./cleanup_claude.sh --repo ${REPO_URL} --backup-dir ${MIRROR_DIR} --push --yes"
fi

echo
echo "Next recommended steps:"
echo "  1) Verify the mirror locally and confirm results (git log/gitattributes/ls-tree as needed)."
echo "  2) When ready, push with --push. After pushing, ask all collaborators to re-clone."
echo "  3) Re-enable branch protections and update any automation that relied on old commit SHAs."

exit 0
