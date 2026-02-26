from studio.utils.jules_client import JulesGitHubClient
from studio.config import get_settings
from pydantic import SecretStr

settings = get_settings()
client = JulesGitHubClient(
    github_token=settings.github_token,
    repo_name=settings.github_repository,
    jules_username=settings.jules_username
)

pulls = client.repo.get_pulls(state='open', head=f"{client.repo.owner.login}:replace-virtual-patching-with-git-checkout")
for pr in pulls:
    print(f"PR Number: {pr.number}")
