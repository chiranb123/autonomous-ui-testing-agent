import os

from dotenv import load_dotenv
from github import Github, Auth

load_dotenv()


class GitHubClient:

    def __init__(self):
        auth = Auth.Token(
            os.getenv("GITHUB_TOKEN")
        )

        self.client = Github(auth=auth)

    def get_repo(self, repo_name: str):
        return self.client.get_repo(repo_name)