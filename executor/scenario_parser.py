# executor/scenario_parser.py

class ScenarioParser:

    def parse(
            self,
            feature_text
    ):

        steps = []

        for line in feature_text.splitlines():

            line = line.strip()

            if line.startswith(
                    (
                            "Given",
                            "When",
                            "Then",
                            "And"
                    )
            ):

                keyword = (
                    line.split()[0]
                )

                text = (
                    line[len(keyword):]
                    .strip()
                )

                steps.append(
                    {
                        "keyword": keyword,
                        "text": text
                    }
                )

        return steps