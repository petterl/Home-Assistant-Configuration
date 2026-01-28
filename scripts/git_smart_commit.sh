#!/bin/bash
# Smart commit script - generates relevant commit messages based on changed files
# Usage: git_smart_commit.sh [optional custom message]

cd /config

# Check if there are changes to commit
if [ -z "$(git status --porcelain)" ]; then
    echo "NO_CHANGES"
    exit 0
fi

# Get changed files
CHANGED=$(git diff --name-only HEAD 2>/dev/null)
STAGED=$(git diff --name-only --cached 2>/dev/null)
UNTRACKED=$(git ls-files --others --exclude-standard 2>/dev/null)

# Combine all changes
ALL_CHANGES=$(echo -e "${CHANGED}\n${STAGED}\n${UNTRACKED}" | grep -v '^$' | sort -u)

# If custom message provided, use it
if [ -n "$1" ]; then
    MESSAGE="$1"
else
    # Generate smart message based on files
    PARTS=()

    if echo "$ALL_CHANGES" | grep -q "^automations.yaml"; then
        PARTS+=("automations")
    fi

    if echo "$ALL_CHANGES" | grep -q "^configuration.yaml"; then
        PARTS+=("configuration")
    fi

    if echo "$ALL_CHANGES" | grep -q "^template_sensors.yaml"; then
        PARTS+=("template sensors")
    fi

    if echo "$ALL_CHANGES" | grep -q "^scripts.yaml"; then
        PARTS+=("scripts")
    fi

    if echo "$ALL_CHANGES" | grep -q "^scenes.yaml"; then
        PARTS+=("scenes")
    fi

    if echo "$ALL_CHANGES" | grep -q "^esphome/"; then
        PARTS+=("ESPHome")
    fi

    if echo "$ALL_CHANGES" | grep -q "^zigbee2mqtt/"; then
        PARTS+=("Zigbee2MQTT")
    fi

    if echo "$ALL_CHANGES" | grep -q "^dashboards/"; then
        PARTS+=("dashboards")
    fi

    if echo "$ALL_CHANGES" | grep -q "^CLAUDE.md"; then
        PARTS+=("Claude instructions")
    fi

    if echo "$ALL_CHANGES" | grep -q "^.gitignore"; then
        PARTS+=("gitignore")
    fi

    if echo "$ALL_CHANGES" | grep -q "^scripts/"; then
        PARTS+=("utility scripts")
    fi

    # Build message
    if [ ${#PARTS[@]} -eq 0 ]; then
        MESSAGE="Update config files"
    elif [ ${#PARTS[@]} -eq 1 ]; then
        MESSAGE="Update ${PARTS[0]}"
    elif [ ${#PARTS[@]} -eq 2 ]; then
        MESSAGE="Update ${PARTS[0]} and ${PARTS[1]}"
    else
        LAST="${PARTS[-1]}"
        unset 'PARTS[-1]'
        MESSAGE="Update $(IFS=', '; echo "${PARTS[*]}") and ${LAST}"
    fi
fi

echo "$MESSAGE"
