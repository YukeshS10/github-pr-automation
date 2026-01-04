#!/usr/bin/env python3
"""
Sequential PR Creation Tool for GitHub Enterprise by Yuks
Automatically creates PRs across environments (Quality -> PreProd -> Production)
"""

import os
import sys
import subprocess
import requests
from datetime import datetime
from typing import Optional, Tuple, List, Dict
import argparse
from dotenv import load_dotenv

load_dotenv()


class Colors:
    """Terminal colors for better output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


class GitHubPRAutomation:
    """Handles automated PR creation across multiple environments"""
    
    ALL_ENVIRONMENTS = [
        {'name': 'Quality', 'branch': 'quality', 'suffix': 'qas', 'title_prefix': 'dev-qas', 'key': 'qas'},
        {'name': 'PreProduction', 'branch': 'preprd', 'suffix': 'stg', 'title_prefix': 'qas-stg', 'key': 'stg'},
        {'name': 'Production', 'branch': 'main', 'suffix': 'main', 'title_prefix': 'stg-main', 'key': 'main'}
    ]
    
    def __init__(self, github_token: str, repo_owner: str, repo_name: str, 
                 reviewers: List[str] = None,
                 environments: List[str] = None,
                 github_api_url: str = "https://api.github.com",
                 cherry_pick_commits: List[str] = None):
        """Initialize the PR automation tool"""
        self.github_token = github_token
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.reviewers = reviewers or []
        self.github_api_url = github_api_url.rstrip('/')
        self.api_base = f"{self.github_api_url}/repos/{repo_owner}/{repo_name}"
        self.cherry_pick_commits = cherry_pick_commits or []
        
        self.headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json',
            'Content-Type': 'application/json'
        }
        
        self.pr_numbers = {}
        
        # Filter environments based on config
        if environments:
            self.environments = [env for env in self.ALL_ENVIRONMENTS if env['key'] in environments]
            if not self.environments:
                raise ValueError(f"No valid environments found. Available: qas, stg, main")
        else:
            self.environments = self.ALL_ENVIRONMENTS
    
    def print_header(self, text: str):
        """Print a formatted header"""
        print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
        print(f"{Colors.HEADER}{Colors.BOLD}{text.center(70)}{Colors.ENDC}")
        print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")
    
    def print_success(self, text: str):
        print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")
    
    def print_error(self, text: str):
        print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")
    
    def print_warning(self, text: str):
        print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")
    
    def print_info(self, text: str):
        print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")
    
    def run_git_command(self, command: list, check: bool = True) -> Tuple[bool, str]:
        """Execute a git command"""
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=check
            )
            return True, result.stdout.strip()
        except subprocess.CalledProcessError as e:
            return False, e.stderr.strip()
    
    def check_branch_exists(self, branch_name: str) -> bool:
        """Check if a branch exists remotely"""
        success, _ = self.run_git_command(
            ['git', 'rev-parse', '--verify', f'origin/{branch_name}'],
            check=False
        )
        return success
    
    def fetch_all_latest_changes(self):
        """Fetch latest changes from all remote branches"""
        self.run_git_command(['git', 'fetch', '--all', '--prune'], check=False)
        
        success, current_branch = self.run_git_command(['git', 'branch', '--show-current'], check=False)
        if success and current_branch:
            self.run_git_command(['git', 'pull', 'origin', current_branch], check=False)
    
    def validate_cherry_pick_commits(self) -> bool:
        """Validate that cherry-pick commits exist"""
        self.print_header("Validating Cherry-Pick Commits")
        
        all_valid = True
        for commit_hash in self.cherry_pick_commits:
            success, output = self.run_git_command(
                ['git', 'cat-file', '-t', commit_hash],
                check=False
            )
            
            if success and output == 'commit':
                success, msg = self.run_git_command(
                    ['git', 'log', '-1', '--pretty=format:%s', commit_hash],
                    check=False
                )
                self.print_success(f"Commit {commit_hash[:8]}: {msg}")
            else:
                self.print_error(f"Commit {commit_hash} not found")
                all_valid = False
        
        return all_valid
    
    def validate_prerequisites(self, base_branch: str) -> bool:
        """Validate all prerequisites before starting"""
        self.print_header("Validating Prerequisites")
        self.print_info("Fetching Latest Changes")
        
        all_valid = True
        
        # Check if base branch exists
        if not self.check_branch_exists(base_branch):
            self.print_error(f"Base branch '{base_branch}' does not exist")
            all_valid = False
        else:
            self.print_success(f"Base branch '{base_branch}' exists")
        
        # Validate cherry-pick commits
        if self.cherry_pick_commits:
            if not self.validate_cherry_pick_commits():
                all_valid = False
        
        # Check git repository
        success, _ = self.run_git_command(['git', 'rev-parse', '--git-dir'], check=False)
        if not success:
            self.print_error("Not in a git repository")
            all_valid = False
        
        # Check for uncommitted changes
        success, output = self.run_git_command(['git', 'status', '--porcelain'], check=False)
        if success and output:
            self.print_warning("You have uncommitted changes in your working directory")
            self.print_info("This won't affect the automation, but consider committing them")
        
        return all_valid
    
    def get_commit_messages(self, base_branch: str, target_branch: str) -> List[str]:
        """Get commit messages between base branch and target branch"""
        self.print_info(f"Fetching commit messages from {base_branch}...")
        
        self.run_git_command(['git', 'fetch', 'origin', base_branch], check=False)
        self.run_git_command(['git', 'fetch', 'origin', target_branch], check=False)
        
        success, output = self.run_git_command(
            ['git', 'log', f'origin/{target_branch}..origin/{base_branch}', 
             '--pretty=format:%s', '--no-merges'],
            check=False
        )
        
        if success and output:
            commits = [line.strip() for line in output.split('\n') if line.strip()]
            self.print_success(f"Found {len(commits)} commit(s)")
            return commits
        else:
            self.print_warning("No commits found or error fetching commits")
            return []
    
    def get_cherry_pick_commit_messages(self) -> List[str]:
        """Get commit messages for cherry-pick commits"""
        messages = []
        for commit_hash in self.cherry_pick_commits:
            success, msg = self.run_git_command(
                ['git', 'log', '-1', '--pretty=format:%s', commit_hash],
                check=False
            )
            if success:
                messages.append(f"{commit_hash[:8]} - {msg}")
        return messages
    
    def generate_pr_description(self, commits: List[str], max_commits: int = 10) -> str:
        """Generate a formatted description from commit messages"""
        if not commits:
            return "_No new commits to describe_"
        
        description_lines = []
        
        for i, commit in enumerate(commits[:max_commits], 1):
            description_lines.append(f"{i}. {commit}")
        
        if len(commits) > max_commits:
            remaining = len(commits) - max_commits
            description_lines.append(f"_...and {remaining} more commit(s)_")
        
        return "\n".join(description_lines)
    
    def create_staging_branch_with_merge(self, base_branch: str, target_branch: str, suffix: str) -> Optional[Tuple[str, bool]]:
        """Create staging branch from target and merge base branch"""
        safe_base_branch = base_branch.replace('/', '-')
        timestamp = datetime.now().strftime('%H%M')
        staging_branch = f"{safe_base_branch}-{timestamp}-{suffix}"

        self.print_info(
            f"Creating staging branch: {staging_branch} "
            f"(from {target_branch}, merging {base_branch})"
        )

        success, output = self.run_git_command(['git', 'fetch', 'origin', target_branch], check=False)
        if not success:
            self.print_error(f"Failed to fetch {target_branch}: {output}")
            return None
        
        self.run_git_command(['git', 'fetch', 'origin', base_branch], check=False)

        success, output = self.run_git_command(
            ['git', 'checkout', '-b', staging_branch, f'origin/{target_branch}'],
            check=False
        )
        if not success:
            self.print_error(f"Failed to create staging branch: {output}")
            return None

        success, output = self.run_git_command(
            ['git', 'merge', '--no-ff', f'origin/{base_branch}'],
            check=False
        )

        has_conflicts = not success
        
        if has_conflicts:
            self.print_warning("Merge conflicts detected during branch creation")
            self.print_info(f"Conflict details:\n{output}")
            self.run_git_command(['git', 'merge', '--abort'], check=False)
            self.print_info("Merge aborted - conflicts must be resolved before pushing")
            return (staging_branch, True)
        
        success, output = self.run_git_command(
            ['git', 'push', '-u', 'origin', staging_branch],
            check=False
        )
        if not success:
            self.print_error(f"Failed to push staging branch: {output}")
            return None

        return (staging_branch, False)

    def create_staging_branch_with_cherry_pick(self, base_branch: str, target_branch: str, suffix: str) -> Optional[Tuple[str, bool]]:
        """Create staging branch from target and cherry-pick commits"""
        safe_base_branch = base_branch.replace('/', '-')
        timestamp = datetime.now().strftime('%H%M')
        staging_branch = f"{safe_base_branch}-{timestamp}-{suffix}"

        self.print_info(
            f"Creating staging branch: {staging_branch} "
            f"(from {target_branch}, cherry-picking {len(self.cherry_pick_commits)} commit(s))"
        )

        success, output = self.run_git_command(['git', 'fetch', 'origin', target_branch], check=False)
        if not success:
            self.print_error(f"Failed to fetch {target_branch}: {output}")
            return None

        success, output = self.run_git_command(
            ['git', 'checkout', '-b', staging_branch, f'origin/{target_branch}'],
            check=False
        )
        if not success:
            self.print_error(f"Failed to create staging branch: {output}")
            return None

        # Cherry-pick each commit
        has_conflicts = False
        for commit_hash in self.cherry_pick_commits:
            self.print_info(f"Cherry-picking {commit_hash[:8]}...")
            success, output = self.run_git_command(
                ['git', 'cherry-pick', commit_hash],
                check=False
            )
            
            if not success:
                self.print_warning(f"Cherry-pick conflict for {commit_hash[:8]}")
                self.print_info(f"Conflict details:\n{output}")
                self.run_git_command(['git', 'cherry-pick', '--abort'], check=False)
                has_conflicts = True
                break
        
        if has_conflicts:
            self.print_info("Cherry-pick aborted - conflicts must be resolved before pushing")
            return (staging_branch, True)
        
        success, output = self.run_git_command(
            ['git', 'push', '-u', 'origin', staging_branch],
            check=False
        )
        if not success:
            self.print_error(f"Failed to push staging branch: {output}")
            return None

        self.print_success(f"All commits cherry-picked successfully")
        return (staging_branch, False)
    
    def wait_for_conflict_resolution_merge(self, staging_branch: str, target_branch: str, base_branch: str, env_name: str) -> bool:
        """Guide user through merge conflict resolution"""
        self.print_warning(f"\n{'='*70}")
        self.print_warning("MERGE CONFLICT RESOLUTION REQUIRED")
        self.print_warning(f"{'='*70}")
        
        print(f"\n{Colors.BOLD}Environment:{Colors.ENDC} {env_name}")
        print(f"{Colors.BOLD}Staging Branch:{Colors.ENDC} {staging_branch}")
        print(f"{Colors.BOLD}Target Branch:{Colors.ENDC} {target_branch}")
        print(f"{Colors.BOLD}Base Branch:{Colors.ENDC} {base_branch}")
        
        print(f"\n{Colors.OKCYAN}Steps to resolve:{Colors.ENDC}")
        print(f"  1. Checkout: {Colors.BOLD}git checkout {staging_branch}{Colors.ENDC}")
        print(f"  2. Merge: {Colors.BOLD}git merge --no-ff origin/{base_branch}{Colors.ENDC}")
        print(f"  3. Resolve conflicts in your editor")
        print(f"  4. Stage files: {Colors.BOLD}git add .{Colors.ENDC}")
        print(f"  5. Commit: {Colors.BOLD}git commit{Colors.ENDC}")
        print(f"  6. Push: {Colors.BOLD}git push -u origin {staging_branch}{Colors.ENDC}")
        
        return self._wait_for_resolution(staging_branch, env_name, base_branch)

    def wait_for_conflict_resolution_cherry_pick(self, staging_branch: str, env_name: str) -> bool:
        """Guide user through cherry-pick conflict resolution"""
        self.print_warning(f"\n{'='*70}")
        self.print_warning("CHERRY-PICK CONFLICT RESOLUTION REQUIRED")
        self.print_warning(f"{'='*70}")
        
        print(f"\n{Colors.BOLD}Environment:{Colors.ENDC} {env_name}")
        print(f"{Colors.BOLD}Staging Branch:{Colors.ENDC} {staging_branch}")
        print(f"{Colors.BOLD}Commits to cherry-pick:{Colors.ENDC}")
        for commit in self.cherry_pick_commits:
            print(f"  - {commit[:8]}")
        
        print(f"\n{Colors.OKCYAN}Steps to resolve:{Colors.ENDC}")
        print(f"  1. Checkout: {Colors.BOLD}git checkout {staging_branch}{Colors.ENDC}")
        print(f"  2. Cherry-pick each commit:")
        for commit in self.cherry_pick_commits:
            print(f"     {Colors.BOLD}git cherry-pick {commit}{Colors.ENDC}")
        print(f"  3. Resolve conflicts if any")
        print(f"  4. Stage files: {Colors.BOLD}git add .{Colors.ENDC}")
        print(f"  5. Continue: {Colors.BOLD}git cherry-pick --continue{Colors.ENDC}")
        print(f"  6. Repeat for remaining commits")
        print(f"  7. Push: {Colors.BOLD}git push -u origin {staging_branch}{Colors.ENDC}")
        
        return self._wait_for_resolution(staging_branch, env_name, None)
    
    def _wait_for_resolution(self, staging_branch: str, env_name: str, base_branch: Optional[str]) -> bool:
        """Common conflict resolution wait logic"""
        self.run_git_command(['git', 'checkout', staging_branch], check=False)
        
        if base_branch:
            self.print_info("\nAttempting merge to show conflicts...")
            self.run_git_command(['git', 'merge', '--no-ff', f'origin/{base_branch}'], check=False)
        else:
            self.print_info("\nAttempting cherry-pick to show conflicts...")
            for commit in self.cherry_pick_commits:
                success, _ = self.run_git_command(['git', 'cherry-pick', commit], check=False)
                if not success:
                    break
        
        while True:
            print(f"\n{Colors.BOLD}What would you like to do?{Colors.ENDC}")
            print("  1. I've resolved conflicts and pushed - Continue")
            print("  2. Skip this environment")
            print("  3. Stop entire process")
            
            choice = input(f"\n{Colors.OKCYAN}Enter choice (1/2/3): {Colors.ENDC}").strip()
            
            if choice == '1':
                self.print_info("Verifying conflict resolution...")
                
                self.run_git_command(['git', 'fetch', 'origin', staging_branch], check=False)
                
                success, _ = self.run_git_command(
                    ['git', 'rev-parse', f'origin/{staging_branch}'],
                    check=False
                )
                
                if not success:
                    self.print_error(f"Branch {staging_branch} not found on remote")
                    self.print_error(f"Please push: git push -u origin {staging_branch}")
                    continue
                
                success, output = self.run_git_command(['git', 'status', '--porcelain'], check=False)
                
                if success and output:
                    self.print_warning("You have uncommitted changes")
                    self.print_info("Please commit and push all changes")
                    continue
                
                self.print_success("Conflicts resolved and branch pushed!")
                return True
            
            elif choice == '2':
                self.print_warning(f"Skipping {env_name} environment")
                self.run_git_command(['git', 'merge', '--abort'], check=False)
                self.run_git_command(['git', 'cherry-pick', '--abort'], check=False)
                return False
            
            elif choice == '3':
                self.print_warning("Stopping entire process")
                self.run_git_command(['git', 'merge', '--abort'], check=False)
                self.run_git_command(['git', 'cherry-pick', '--abort'], check=False)
                sys.exit(0)
            
            else:
                self.print_error("Invalid choice. Please enter 1, 2, or 3")
    
    def add_reviewers_to_pr(self, pr_number: int) -> bool:
        """Add reviewers to a pull request"""
        if not self.reviewers:
            return True
        
        self.print_info(f"Adding reviewers: {', '.join(self.reviewers)}")
        
        reviewer_data = {'reviewers': self.reviewers}
        
        try:
            response = requests.post(
                f"{self.api_base}/pulls/{pr_number}/requested_reviewers",
                headers=self.headers,
                json=reviewer_data
            )
            
            if response.status_code in [201, 200]:
                self.print_success("Reviewers added successfully")
                return True
            else:
                self.print_warning(f"Failed to add reviewers: {response.status_code}")
                return False
                
        except Exception as e:
            self.print_warning(f"Exception while adding reviewers: {str(e)}")
            return False
    
    def create_pull_request(self, staging_branch: str, target_branch: str, 
                          env_name: str, source_reference: str, title_prefix: str) -> Optional[Dict]:
        """Create a pull request using GitHub API"""
        self.print_info(f"Creating pull request for {env_name}...")
        
        # Get commit messages
        if self.cherry_pick_commits:
            commits = self.get_cherry_pick_commit_messages()
            commit_description = self.generate_pr_description(commits)
            operation_type = "Cherry-Pick"
        else:
            commits = self.get_commit_messages(source_reference, target_branch)
            commit_description = self.generate_pr_description(commits)
            operation_type = "Merge"
        
        # Build PR references
        pr_references = ""
        if env_name == "PreProduction" and "Quality" in self.pr_numbers:
            pr_references = f"\n\n### Related PRs\n- Quality: #{self.pr_numbers['Quality']}"
        elif env_name == "Production":
            refs = []
            if "Quality" in self.pr_numbers:
                refs.append(f"Quality: #{self.pr_numbers['Quality']}")
            if "PreProduction" in self.pr_numbers:
                refs.append(f"PreProduction: #{self.pr_numbers['PreProduction']}")
            if refs:
                pr_references = f"\n\n### Related PRs\n" + "\n".join(f"- {ref}" for ref in refs)
        
        env_index = next((i for i, e in enumerate(self.environments) if e['name'] == env_name), None)
        
        previous_envs = ""
        if env_index and env_index > 0:
            prev_names = [self.environments[i]['name'] for i in range(env_index)]
            previous_envs = f"\n_Previous: {' ✓ | '.join(prev_names)} ✓_"
        
        next_envs = ""
        if env_index is not None and env_index < len(self.environments) - 1:
            next_names = [self.environments[i]['name'] for i in range(env_index + 1, len(self.environments))]
            next_envs = f"\n_Next: {' → '.join(next_names)}_"
        
        warning = ""
        if env_name == "Production":
            warning = "\n\n⚠️ **PRODUCTION DEPLOYMENT** - Review carefully before merging."
        
        pr_data = {
            'title': f"{title_prefix}: {source_reference}",
            'head': staging_branch,
            'base': target_branch,
            'body': f"""
**Source:** `{source_reference}`

### Changes
{commit_description}
{pr_references}

---
{previous_envs}{next_envs}{warning}

_Created by PR Automation Tool at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_
"""
        }
        
        try:
            response = requests.post(
                f"{self.api_base}/pulls",
                headers=self.headers,
                json=pr_data
            )
            
            if response.status_code == 201:
                pr_data = response.json()
                pr_url = pr_data['html_url']
                pr_number = pr_data['number']
                
                self.print_success(f"Pull request created: {pr_url}")
                self.add_reviewers_to_pr(pr_number)
                
                return {'url': pr_url, 'number': pr_number}
            else:
                self.print_error(f"Failed to create PR: {response.status_code}")
                self.print_error(f"Response: {response.text}")
                return None
                
        except Exception as e:
            self.print_error(f"Exception while creating PR: {str(e)}")
            return None
    
    def process_environment(self, base_branch: str, env_config: dict) -> dict:
        """Process a single environment"""
        env_name = env_config['name']
        target_branch = env_config['branch']
        suffix = env_config['suffix']
        title_prefix = env_config['title_prefix']
        
        self.print_header(f"Processing {env_name} Environment")
        
        result = {
            'environment': env_name,
            'success': False,
            'staging_branch': None,
            'pr_url': None,
            'pr_number': None,
            'has_conflicts': False,
            'skipped': False
        }
        
        # Create staging branch based on mode
        if self.cherry_pick_commits:
            branch_result = self.create_staging_branch_with_cherry_pick(base_branch, target_branch, suffix)
            source_reference = f"{base_branch}"
        else:
            branch_result = self.create_staging_branch_with_merge(base_branch, target_branch, suffix)
            source_reference = base_branch
        
        if not branch_result:
            self.print_error(f"Failed to create staging branch for {env_name}")
            return result
        
        staging_branch, has_conflicts = branch_result
        result['staging_branch'] = staging_branch
        result['has_conflicts'] = has_conflicts
        
        # Handle conflicts
        if has_conflicts:
            if self.cherry_pick_commits:
                resolved = self.wait_for_conflict_resolution_cherry_pick(staging_branch, env_name)
            else:
                resolved = self.wait_for_conflict_resolution_merge(
                    staging_branch, target_branch, base_branch, env_name
                )
            
            if not resolved:
                result['skipped'] = True
                return result
            
            self.print_success("Ready to create pull request")
        
        # Create PR
        pr_info = self.create_pull_request(
            staging_branch, 
            target_branch, 
            env_name,
            source_reference,
            title_prefix
        )
        
        if pr_info:
            result['success'] = True
            result['pr_url'] = pr_info['url']
            result['pr_number'] = pr_info['number']
            self.pr_numbers[env_name] = pr_info['number']
        
        return result
    
    def run(self, base_branch: str):
        """Main execution flow"""
        self.print_header("Sequential PR Creation Tool")
        print(f"{Colors.BOLD}Repository:{Colors.ENDC} {self.repo_owner}/{self.repo_name}")
        print(f"{Colors.BOLD}Base Branch:{Colors.ENDC} {base_branch}")
        
        if self.cherry_pick_commits:
            print(f"{Colors.BOLD}Mode:{Colors.ENDC} Cherry-Pick")
            print(f"{Colors.BOLD}Commits:{Colors.ENDC}")
            for commit in self.cherry_pick_commits:
                print(f"  - {commit[:8]}")
        else:
            print(f"{Colors.BOLD}Mode:{Colors.ENDC} Merge")
        
        print(f"{Colors.BOLD}Target Environments:{Colors.ENDC} {', '.join([e['name'] for e in self.environments])}")
        if self.reviewers:
            print(f"{Colors.BOLD}Reviewers:{Colors.ENDC} {', '.join(self.reviewers)}")
        print(f"{Colors.BOLD}Timestamp:{Colors.ENDC} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Fetch all latest changes
        self.fetch_all_latest_changes()
        
        # Validate prerequisites
        if not self.validate_prerequisites(base_branch):
            self.print_error("\nValidation failed. Fix issues above.")
            sys.exit(1)
        
        results = []
        
        for env_config in self.environments:
            result = self.process_environment(base_branch, env_config)
            results.append(result)
            
            if result['skipped']:
                self.print_info(f"Continuing to next environment...")
                print()
                continue
            
            if not result['success'] and not result['has_conflicts']:
                self.print_warning(f"Stopping at {env_config['name']} due to failure")
                break
            
            print()
        
        # Print summary
        self.print_header("Execution Summary")
        
        for result in results:
            env = result['environment']
            if result['success']:
                print(f"{Colors.OKGREEN}✓ {env}:{Colors.ENDC}")
                print(f"  Branch: {result['staging_branch']}")
                print(f"  PR #{result['pr_number']}: {result['pr_url']}")
            elif result['skipped']:
                print(f"{Colors.WARNING}⊘ {env}: Skipped by user{Colors.ENDC}")
                print(f"  Branch: {result['staging_branch']}")
            elif result['has_conflicts']:
                print(f"{Colors.WARNING}⚠ {env}: Conflicts detected{Colors.ENDC}")
                print(f"  Branch: {result['staging_branch']}")
            else:
                print(f"{Colors.FAIL}✗ {env}: Failed{Colors.ENDC}")
            print()
        
        successful = [r for r in results if r['success']]
        skipped = [r for r in results if r['skipped']]
        
        if len(successful) == len(self.environments):
            self.print_success("All PRs created successfully! 🎉")
        elif successful:
            self.print_success(f"{len(successful)} PR(s) created successfully")
            if skipped:
                self.print_info(f"{len(skipped)} environment(s) skipped")
        else:
            self.print_warning("No PRs were created")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Automated PR creation tool for GitHub Enterprise',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Merge mode - merge entire branch
  %(prog)s -b feature/new-feature
  %(prog)s -b bugfix/fix-123
  
  # Cherry-pick mode - cherry-pick specific commits
  %(prog)s -b feature/hotfix --cherry-pick 2a86c582aa4bfd50f241557077602833ab6096e5
  %(prog)s -b bugfix/security --cherry-pick abc1234 def5678 ghi9012

Environment Variables:
  GITHUB_TOKEN     GitHub personal access token (required)
  GITHUB_REPO      Repository in format 'owner/repo' (required)
  GITHUB_API_URL   GitHub API URL (optional, defaults to github.com)
  PR_REVIEWERS     Comma-separated list of GitHub usernames (optional)
  PR_ENVS          Comma-separated list of environments: qas,stg,main (optional)
"""
    )

    parser.add_argument(
        '-b', '--base-branch',
        required=True,
        help='Base branch name (required for both merge and cherry-pick modes)'
    )
    
    parser.add_argument(
        '--cherry-pick',
        nargs='+',
        help='Commit hash(es) to cherry-pick. If omitted, entire branch will be merged (space-separated)'
    )

    args = parser.parse_args()

    # ENV VALIDATION
    github_token = os.getenv("GITHUB_TOKEN")
    github_repo = os.getenv("GITHUB_REPO")

    if not github_token:
        print("❌ GITHUB_TOKEN is not set")
        sys.exit(1)

    if not github_repo or "/" not in github_repo:
        print("❌ GITHUB_REPO must be set as 'owner/repo'")
        sys.exit(1)

    repo_owner, repo_name = github_repo.split("/", 1)

    # REVIEWERS
    reviewers = None
    env_reviewers = os.getenv("PR_REVIEWERS")
    if env_reviewers:
        reviewers = [r.strip() for r in env_reviewers.split(",") if r.strip()]

    # ENVIRONMENTS
    environments = None
    env_envs = os.getenv("PR_ENVS")
    if env_envs:
        environments = [e.strip() for e in env_envs.split(",") if e.strip()]

    # RUN AUTOMATION
    automation = GitHubPRAutomation(
        github_token=github_token,
        repo_owner=repo_owner,
        repo_name=repo_name,
        reviewers=reviewers,
        environments=environments,
        github_api_url=os.getenv('GITHUB_API_URL', 'https://api.github.com'),
        cherry_pick_commits=args.cherry_pick
    )

    automation.run(args.base_branch)


if __name__ == "__main__":
    main()