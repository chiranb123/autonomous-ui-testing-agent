from models.verification_result import (
    VerificationResult
)


class VerificationEngine:

    def verify_text_exists(
            self,
            snapshot_text,
            expected_text
    ):

        passed = (
            expected_text.lower()
            in
            snapshot_text.lower()
        )

        return VerificationResult(
            passed=passed,
            expected=expected_text,
            actual=(
                expected_text
                if passed
                else "Not Found"
            ),
            message=(
                "Text found"
                if passed
                else "Text not found"
            )
        )

    def verify_url_contains(
            self,
            current_url,
            expected_fragment
    ):

        passed = (
            expected_fragment.lower()
            in
            current_url.lower()
        )

        return VerificationResult(
            passed=passed,
            expected=expected_fragment,
            actual=current_url,
            message=(
                "URL verified"
                if passed
                else "URL verification failed"
            )
        )
