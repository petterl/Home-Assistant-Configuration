#!/bin/bash
# Git commit and push with smart commit messages
# Usage: git_commit_and_push.sh [optional custom message]

cd /config

# Source secrets for GitHub PAT
GITHUB_PAT=$(grep "github_pat:" /config/secrets.yaml | cut -d' ' -f2)
GITHUB_REPO=$(grep "github_repo:" /config/secrets.yaml | cut -d' ' -f2)

# Check for untracked files first
UNTRACKED=$(git ls-files --others --exclude-standard 2>/dev/null)
if [ -n "$UNTRACKED" ]; then
    echo "UNTRACKED_FILES"
    echo "$UNTRACKED"
    exit 1
fi

# Check if there are changes
if [ -z "$(git status --porcelain)" ]; then
    echo "NO_CHANGES"
    exit 0
fi

# Get smart commit message
MESSAGE=$(/config/scripts/git_smart_commit.sh "$1")

# Stage tracked files that have changes (not untracked)
git add -u

# Commit
git commit -m "$MESSAGE"
COMMIT_RESULT=$?

if [ $COMMIT_RESULT -ne 0 ]; then
    echo "COMMIT_FAILED"
    exit 1
fi

# Push
git push "https://${GITHUB_PAT}@github.com/${GITHUB_REPO}.git" master 2>&1
PUSH_RESULT=$?

if [ $PUSH_RESULT -ne 0 ]; then
    echo "PUSH_FAILED"
    exit 1
fi

echo "SUCCESS: $MESSAGE"
