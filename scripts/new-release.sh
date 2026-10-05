#!/usr/bin/env bash
# Create and publish a release: feature -> development -> main.

set -Eeuo pipefail

# Project settings: keep adaptations to other Python projects in this block.
readonly project_name="BMGeoIP"
readonly version_file="bmgeoip/constants/DBMGeoIP.py"
readonly version_constant="VERSION"
readonly codename_constant="CMDB_CODENAME"
readonly changelog_file="CHANGELOG.md"
readonly remote="origin"
readonly dev_branch="dev"
readonly main_branch="main"
readonly feature_prefix="feat/maint-"
readonly python_command="python3"

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

version_number='(0|[1-9][0-9]*)'
prerelease_identifier='(0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)'
version_pattern="^${version_number}\.${version_number}\.${version_number}(-${prerelease_identifier}(\.${prerelease_identifier})*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$"
active_step="initialization"

status() {
    local label=$1 color="" reset=""
    shift
    if [[ -t 1 && -z ${NO_COLOR+x} && ${TERM:-} != dumb ]]; then
        case ${label} in
            PASSED) color=$'\033[32m' ;;
            FAIL) color=$'\033[31m' ;;
            WARNING) color=$'\033[33m' ;;
        esac
        reset=$'\033[0m'
    fi
    printf '[ %s%s%s ] %s\n' "${color}" "${label}" "${reset}" "$*"
}

fail() {
    status FAIL "$*" >&2
    exit 1
}

on_error() {
    local code=$1
    status FAIL "Stopped during ${active_step} (exit ${code}). Inspect the Git state before retrying." >&2
    exit "${code}"
}
trap 'on_error "$?"' ERR

step() {
    active_step=$1
    shift
    "$@"
    status PASSED "${active_step}"
}

# Read literal constants without importing project code. Update only their values,
# preserving annotations, comments, indentation, and the rest of the file.
project_metadata() {
    "${python_command}" - "${version_file}" "${version_constant}" "${codename_constant}" "$@" <<'PY'
import ast
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
keys = sys.argv[2:4]
mode = sys.argv[4]
source = path.read_bytes()
tree = ast.parse(source, filename=str(path))
values = []
for key in keys:
    matches = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            targets = node.targets
        else:
            continue
        if any(isinstance(target, ast.Name) and target.id == key for target in targets):
            if len(targets) != 1:
                sys.exit(f"{key} must have its own assignment.")
            matches.append(node.value)
    if len(matches) != 1:
        sys.exit(f"{path} must contain exactly one {key} assignment.")
    value = matches[0]
    if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
        sys.exit(f"{key} must be a literal string.")
    if value.lineno != value.end_lineno:
        sys.exit(f"{key} must be a single-line literal string.")
    values.append(value)

if mode == "read":
    print(values[0].value)
elif mode == "update":
    lines = source.splitlines(keepends=True)
    # Work backwards so replacements on the same line retain their offsets.
    replacements = sorted(zip(values, sys.argv[5:7]), key=lambda item: (
        item[0].lineno, item[0].col_offset), reverse=True)
    for node, text in replacements:
        index = node.lineno - 1
        literal = json.dumps(text, ensure_ascii=False).encode("utf-8")
        lines[index] = lines[index][:node.col_offset] + literal + lines[index][node.end_col_offset:]
    updated = b"".join(lines)
    ast.parse(updated, filename=str(path))
    path.write_bytes(updated)
else:
    sys.exit(f"Unknown metadata operation: {mode}")
PY
}

current_version() {
    local value
    value=$(project_metadata read) || fail "Cannot read ${project_name} release constants."
    [[ ${value} =~ ${version_pattern} ]] || fail "Cannot read a single valid ${project_name} version."
    printf '%s\n' "${value}"
}

usage() {
    local branch likely_version major minor patch next_version installed_version
    branch=$(git branch --show-current)
    if [[ ${branch} =~ (^|[/_-])v?([0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?)$ ]]; then
        likely_version=${BASH_REMATCH[2]}
    else
        installed_version=$(current_version) || return 1
        IFS=. read -r major minor patch <<< "${installed_version%%[-+]*}"
        likely_version="${major}.${minor}.$((10#${patch} + 1))"
    fi
    IFS=. read -r major minor patch <<< "${likely_version%%[-+]*}"
    next_version="${major}.${minor}.$((10#${patch} + 1))"

    cat <<HELP
Usage: $(basename -- "$0") <version> <message> [next-feature-branch]

Current branch: ${branch}
Likely next version: ${likely_version}

Example:
  $(basename -- "$0") ${likely_version} "Maintenance release"

Next feature branch: ${feature_prefix}${next_version}

Run from a clean feature branch with local ${dev_branch} and ${main_branch} up to date.
Use a version without a leading v. The next branch defaults to
${feature_prefix}<version with patch incremented>.

After interactive confirmation, updates ${version_constant}, ${codename_constant}
in ${version_file} and ${changelog_file}, merges through ${dev_branch} to
${main_branch}, tags and pushes the release, then creates the next local feature
branch. The message becomes the codename. Requires Git and ${python_command}.
HELP
}

validate_arguments() {
    version=$1
    [[ ${version} =~ ${version_pattern} ]] || fail "Use a version such as 0.0.1, without a leading v."
    [[ -n ${2//[[:space:]]/} ]] || fail "A release message is required."
    description=$2
    message="Release ${version}: ${description}"
    tag="v${version}"
    local major minor patch
    IFS=. read -r major minor patch <<< "${version%%[-+]*}"
    next_branch=${3:-"${feature_prefix}${major}.${minor}.$((10#${patch} + 1))"}
}

check_changelog() {
    [[ $(grep -c '^## \[Unreleased\]$' "${changelog_file}") == 1 ]] ||
        fail "${changelog_file} must contain exactly one ## [Unreleased] heading."
    if grep -Fq "## [${version}]" "${changelog_file}"; then
        fail "Version ${version} is already in ${changelog_file}."
    fi
}

preflight_local() {
    source_branch=$(git branch --show-current)
    [[ -n ${source_branch} && ${source_branch} != "${dev_branch}" && ${source_branch} != "${main_branch}" ]] ||
        fail "Run from a feature branch."
    [[ -z $(git status --porcelain) ]] || fail "Commit or stash all changes before releasing."
    git remote get-url "${remote}" >/dev/null || fail "Missing Git remote ${remote}."
    git check-ref-format --branch "${next_branch}" >/dev/null || fail "Invalid next feature branch."
    [[ ${next_branch} != -* && ${next_branch} != '@{-'* ]] || fail "Use a literal next feature branch name."
    if git show-ref --verify --quiet "refs/heads/${next_branch}"; then
        fail "Next feature branch already exists."
    fi
    local branch
    for branch in "${dev_branch}" "${main_branch}"; do
        git show-ref --verify --quiet "refs/heads/${branch}" || fail "Missing local ${branch} branch."
    done
    git ls-files --error-unmatch "${version_file}" "${changelog_file}" >/dev/null ||
        fail "The release constants and changelog files must be committed."
    current_version >/dev/null
    check_changelog
}

preflight_remote() {
    if git show-ref --verify --quiet "refs/tags/${tag}"; then
        fail "Tag ${tag} already exists."
    fi
    if git show-ref --verify --quiet "refs/remotes/${remote}/${next_branch}"; then
        fail "Next feature branch already exists on ${remote}."
    fi
    local branch
    for branch in "${dev_branch}" "${main_branch}"; do
        if git show-ref --verify --quiet "refs/remotes/${remote}/${branch}"; then
            git merge-base --is-ancestor "${remote}/${branch}" "${branch}" ||
                fail "Local ${branch} is behind or diverged from ${remote}/${branch}; update it first."
        else
            status WARNING "Remote ${remote}/${branch} is absent and will be created."
        fi
    done
    git merge-base --is-ancestor "${main_branch}" "${dev_branch}" || fail "Merge ${main_branch} into ${dev_branch} before releasing."
    git merge-base --is-ancestor "${dev_branch}" "${source_branch}" || fail "Merge ${dev_branch} into the feature branch before releasing."
}

confirm_release() {
    printf '\n%s release summary:\n' "${project_name}"
    printf '  Source:       %s\n' "${source_branch}"
    printf '  Tag:          %s\n' "${tag}"
    printf '  Message:      %s\n' "${message}"
    printf '  Codename:     %s\n' "${description}"
    printf '  Next branch:  %s\n' "${next_branch}"
    printf '  Remote:       %s\n\n' "$(git remote get-url "${remote}")"

    [[ -t 0 ]] || fail "Confirmation requires an interactive terminal."
    local reply
    if ! read -r -p "Create and push this release? [y/N] " reply; then
        reply=""
    fi
    if [[ ${reply} != y && ${reply} != Y ]]; then
        status WARNING "Release cancelled."
        exit 0
    fi
}

update_release_files() {
    current_version >/dev/null
    check_changelog
    project_metadata update "${version}" "${description}"
    local release_date
    release_date=$(date '+%Y-%m-%d @ %H:%M')
    sed -i "/^## \[Unreleased\]$/a\\
\\
## [${version}] - ${release_date}" "${changelog_file}"
    git add -- "${version_file}" "${changelog_file}"
    git commit -m "${message}"
}

main() {
    command -v git >/dev/null || fail "Required command not found: git"
    command -v "${python_command}" >/dev/null || fail "Required command not found: ${python_command}"
    if [[ ${1:-} == -h || ${1:-} == --help ]]; then
        usage
        exit 0
    fi
    if [[ $# -lt 2 || $# -gt 3 ]]; then
        usage >&2
        exit 2
    fi
    step "Validate release arguments" validate_arguments "$@"
    step "Check local release prerequisites" preflight_local
    step "Fetch refs from ${remote}" git fetch --prune --tags "${remote}"
    step "Check remote refs and branch ancestry" preflight_remote
    step "Confirm release" confirm_release
    step "Switch to ${dev_branch}" git switch "${dev_branch}"
    step "Merge ${source_branch} into ${dev_branch}" git merge --no-ff "${source_branch}" -m "Merge ${source_branch} for ${tag}"
    step "Update release constants and changelog" update_release_files
    step "Switch to ${main_branch}" git switch "${main_branch}"
    step "Merge ${dev_branch} into ${main_branch}" git merge --no-ff "${dev_branch}" -m "${message}"
    step "Create annotated tag ${tag}" git tag -a "${tag}" -m "${message}"
    step "Switch to ${dev_branch}" git switch "${dev_branch}"
    step "Advance ${dev_branch} to ${main_branch}" git merge --ff-only "${main_branch}"
    step "Push release refs atomically" git push --atomic "${remote}" \
        "refs/heads/${main_branch}:refs/heads/${main_branch}" \
        "refs/heads/${dev_branch}:refs/heads/${dev_branch}" \
        "refs/tags/${tag}:refs/tags/${tag}"
    step "Create next feature branch ${next_branch}" git switch -c "${next_branch}"
    status PASSED "${project_name} release ${tag} published successfully."
}

main "$@"
