from studio.config import get_settings
from github import Github
import logging

logging.basicConfig(level=logging.INFO)
settings = get_settings()
gh = Github(settings.github_token.get_secret_value())
repo = gh.get_repo(settings.github_repository)

print(f"Checking repo: {settings.github_repository}")
# List open PRs
prs = repo.get_pulls(state='open')
for pr in prs:
    print(f"PR #{pr.number}: {pr.title}")
    comments = pr.get_issue_comments()
    for comment in comments:
        print(f"  Comment by {comment.user.login}: {comment.body}")

    review_comments = pr.get_review_comments()
    for comment in review_comments:
        print(f"  Review Comment by {comment.user.login} on {comment.path}:{comment.line}: {comment.body}")

# Also check issues just in case
issues = repo.get_issues(state='open')
for issue in issues:
    if not issue.pull_request:
        print(f"Issue #{issue.number}: {issue.title}")
        comments = issue.get_comments()
        for comment in comments:
            print(f"  Comment by {comment.user.login}: {comment.body}")
