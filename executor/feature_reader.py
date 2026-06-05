from pathlib import Path


class FeatureReader:

    def read_all(self):

        features = []

        for file in sorted(
                Path("testscenarios").glob("*.feature")
        ):

            features.append({
                "name": file.stem,
                "path": str(file),
                "content": file.read_text(
                    encoding="utf-8"
                ),
            })

        return features
