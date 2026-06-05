"""
GitHub Projects v2 reader using GraphQL API.
Fetches all issues from a project filtered by status.
"""

import os
import requests
from dotenv import load_dotenv
from models.issue import Issue

load_dotenv()

_GRAPHQL_URL = "https://api.github.com/graphql"

_QUERY = """
query($login: String!, $projectNumber: Int!) {
  user(login: $login) {
    projectV2(number: $projectNumber) {
      title
      items(first: 100) {
        nodes {
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field {
                  ... on ProjectV2SingleSelectField { name }
                }
              }
            }
          }
          content {
            ... on Issue {
              number
              title
              body
              state
            }
          }
        }
      }
    }
  }
}
"""


class ProjectReader:

    def __init__(self, token: str = None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def fetch_issues_by_status(
        self,
        owner: str,
        project_number: int,
        status_filter: str = "Ready For QA",
    ) -> list[Issue]:
        """
        Return all issues in the project whose Status field matches status_filter.
        """
        response = requests.post(
            _GRAPHQL_URL,
            json={
                "query": _QUERY,
                "variables": {
                    "login": owner,
                    "projectNumber": project_number,
                },
            },
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            raise RuntimeError(f"GraphQL errors: {data['errors']}")

        items = (
            data["data"]["user"]["projectV2"]["items"]["nodes"]
        )

        issues = []
        for item in items:
            # Get Status field value
            status = None
            for fv in item.get("fieldValues", {}).get("nodes", []):
                if fv and fv.get("field", {}).get("name") == "Status":
                    status = fv.get("name")

            if status != status_filter:
                continue

            content = item.get("content")
            if not content or "number" not in content:
                continue

            issues.append(Issue(
                number=content["number"],
                title=content["title"],
                body=content.get("body") or "",
            ))

        return issues

