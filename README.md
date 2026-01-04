# GitHub PR Automation Tool

Automate pull request creation across multiple environments (Quality → PreProduction → Production) with support for both branch merging and cherry-picking commits.

## Features

- ✅ **Dual Mode Operation**: Branch merge or cherry-pick commits
- 🔄 **Sequential Environment Promotion**: Quality → PreProd → Production
- ⚠️ **Conflict Detection**: Automatic detection with guided resolution
- 👥 **Auto-Reviewers**: Automatically add reviewers to PRs

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
# Install dependencies
``
pip install requests python-dotenv
``
- GitHub Personal Access Token with `repo` permissions

### 2. Configuration

Create a `.env` file in the project directory:

```bash
# Required
GITHUB_TOKEN=ghp_your_token_here
GITHUB_REPO="KaarProducts/k4k-main"

# Optional
PR_REVIEWERS=user1,user2,user3 //adds default reviewers in the PRs
PR_ENVS=qas,stg,main raises to quality, preproduction and main
```

**Getting a GitHub Token:**
1. Go to GitHub → Settings → Developer settings → Personal access tokens
2. Generate new token (classic)
3. Select `repo` scope
4. Copy the token to your `.env` file

---

## Usage

### Mode 1: Branch Merge (Standard Flow)

Merge a feature branch across all environments:

```bash
# Basic usage
python pr-automation.py --b feature/new-feature

```

**What happens:**
1. Creates staging branch from `quality`, merges `feature/new-feature`
2. Creates PR: staging → `quality`
3. Repeats for `preprd` and `main`

---

### Mode 2: Cherry-Pick (Hotfix Flow)

Cherry-pick specific commits across environments:

```bash
# Single commit
python pr-automation.py --b feature/new-feature --cherry-pick 2a86c582aa4bfd50f241557077602833ab6096e5

# Multiple commits (applied in order)
python pr-automation.py --b feature/new-feature --cherry-pick abc1234 def5678 ghi9012

```

**What happens:**
1. Creates staging branch from `quality`, cherry-picks commit(s)
2. Creates PR: staging → `quality`
3. Repeats for `preprd` and `main`

---

## Environment Configuration

### Default Environments

| Environment | Branch | Suffix | PR Title Prefix |
|-------------|--------|--------|-----------------|
| Quality | `quality` | `qas` | `dev-qas` |
| PreProduction | `preprd` | `stg` | `qas-stg` |
| Production | `main` | `main` | `stg-main` |

---

## Conflict Resolution

When conflicts are detected, the tool will:

1. **Pause execution** and display conflict details
2. **Provide resolution steps**
3. **Wait for you to resolve** and push the changes
4. **Verify resolution** before creating the PR

---

## Security Notes

⚠️ **Important Security Practices:**

1. **Never commit `.env` file** to version control
   ```bash
   echo ".env" >> .gitignore
   ```

2. **Use tokens with minimal permissions**
   - Only grant `repo` scope
   - Use fine-grained tokens when possible

3. **Rotate tokens regularly**
   - Change tokens every 90 days
   - Revoke old tokens immediately

---

## Changelog

- ✨ Added cherry-pick support
- ✅ Multi-environment deployment
- ✅ Auto-reviewer assignment
- ✨ Improved conflict resolution workflow
- 🐛 Fixed branch sync issues
- 📝 Enhanced documentation
