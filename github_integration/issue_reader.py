from models.issue import Issue


class IssueReader:

    def __init__(self, repo):
        self.repo = repo

    def read_issue(self, issue_number: int) -> Issue:

        issue = self.repo.get_issue(
            number=issue_number
        )

        return Issue(
            number=issue.number,
            title=issue.title,
            body=issue.body or ""
        )