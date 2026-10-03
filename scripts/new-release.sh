#!/usr/bin/env bash
# Create and publish a BMGeoIP release: feature -> dev -> main.

set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

version_file="bmgeoip/constants/DBMGeoIP.py"
version_number='(0|[1-9][0-9]*)'
prerelease_identifier='(0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)'
version_pattern="^${version_number}\.${version_number}\.${version_number}(-${prerelease_identifier}(\.${prerelease_identifier})*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$"

fail() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

current_version() {
    local value
    value=$(sed -nE 's/^    VERSION: Final\[str\] = "([^"]+)"$/\1/p' "${version_file}") ||
        fail "Cannot read the BMGeoIP version."
    [[ ${value} =~ ${version_pattern} ]] || fail "Cannot read a single valid BMGeoIP version."
    printf '%s\n' "${value}"
}

usage() {
    local branch likely_version major minor patch next_version current_version
    branch=$(git branch --show-current)
    if [[ ${branch} =~ (^|[/_-])v?([0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?)$ ]]; then
        likely_version=${BASH_REMATCH[2]}
    else
        current_version=$(current_version) || return 1
        IFS=. read -r major minor patch <<< "${current_version%%[-+]*}"
        likely_version="${major}.${minor}.$((10#${patch} + 1))"
    fi
    IFS=. read -r major minor patch <<< "${likely_version%%[-+]*}"
    next_version="${major}.${minor}.$((10#${patch} + 1))"

    cat <<EOF
Usage: $(basename -- "$0") <version> <message> [next-feature-branch]

Current branch: ${branch}
Likely next version: ${likely_version}

Example:
  $(basename -- "$0") ${likely_version} "Maintenance release"

Next feature branch: feat/maint-${next_version}

Run from a clean feature branch with local dev and main up to date.
Use a version without a leading v. The next branch defaults to
feat/maint-<version with patch incremented>.

Updates DBMGeoIP.VERSION and CHANGELOG.md, merges through dev to main, tags and
pushes the release, then creates the next local feature branch.
EOF
}

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
    usage
    exit 0
fi
if [[ $# -lt 2 || $# -gt 3 ]]; then
    usage >&2
    exit 2
fi

version=$1
# Validate before using the version in arithmetic, sed expressions, or Git refs.
if [[ ! ${version} =~ ${version_pattern} ]]; then
    fail "Use a version such as 0.0.1, without a leading v."
fi
[[ -n ${2//[[:space:]]/} ]] || fail "A release message is required."
message="Release ${version}: $2"
tag="v${version}"
IFS=. read -r major minor patch <<< "${version%%[-+]*}"
next_branch=${3:-"feat/maint-${major}.${minor}.$((10#${patch} + 1))"}
source_branch=$(git branch --show-current)
release_date=$(date '+%Y-%m-%d @ %H:%M')

[[ -n ${source_branch} && ${source_branch} != dev && ${source_branch} != main ]] ||
    fail "Run from a feature branch."
[[ -z $(git status --porcelain) ]] || fail "Commit or stash all changes before releasing."
git check-ref-format --branch "${next_branch}" >/dev/null || fail "Invalid next feature branch."
[[ ${next_branch} != -* && ${next_branch} != '@{-'* ]] || fail "Use a literal next feature branch name."
git show-ref --verify --quiet "refs/heads/${next_branch}" && fail "Next feature branch already exists."
for branch in dev main; do
    git show-ref --verify --quiet "refs/heads/${branch}" || fail "Missing local ${branch} branch."
done
git ls-files --error-unmatch "${version_file}" CHANGELOG.md >/dev/null ||
    fail "The BMGeoIP version file and CHANGELOG.md must be committed."
current_version >/dev/null
[[ $(grep -c '^## \[Unreleased\]$' CHANGELOG.md) == 1 ]] ||
    fail "CHANGELOG.md must contain exactly one ## [Unreleased] heading."
if grep -Fq "## [${version}]" CHANGELOG.md; then
    fail "Version ${version} is already in CHANGELOG.md."
fi

git fetch --prune --tags origin
git show-ref --verify --quiet "refs/tags/${tag}" && fail "Tag ${tag} already exists."
git show-ref --verify --quiet "refs/remotes/origin/${next_branch}" &&
    fail "Next feature branch already exists on origin."
for branch in dev main; do
    if git show-ref --verify --quiet "refs/remotes/origin/${branch}"; then
        git merge-base --is-ancestor "origin/${branch}" "${branch}" ||
            fail "Local ${branch} is behind or diverged from origin/${branch}; update it first."
    fi
done
git merge-base --is-ancestor main dev || fail "Merge main into dev before releasing."
git merge-base --is-ancestor dev "${source_branch}" || fail "Merge dev into the feature branch before releasing."

git switch dev
git merge --no-ff "${source_branch}" -m "Merge ${source_branch} for ${tag}"

current_version >/dev/null
sed -i -E "s/^(    VERSION: Final\[str\] = )\"[^\"]+\"$/\1\"${version}\"/" "${version_file}"
sed -i "/^## \[Unreleased\]$/a\\
\\
## [${version}] - ${release_date}" CHANGELOG.md
git add -- "${version_file}" CHANGELOG.md
git commit -m "${message}"

git switch main
git merge --no-ff dev -m "${message}"
git tag -a "${tag}" -m "${message}"

git switch dev
git merge --ff-only main
git push --atomic origin main dev "refs/tags/${tag}"
git switch -c "${next_branch}"
