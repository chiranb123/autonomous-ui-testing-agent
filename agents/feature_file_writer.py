from pathlib import Path


class FeatureFileWriter:

    def write(self, scenarios) -> list[str]:
        output_folder = Path("testscenarios")
        output_folder.mkdir(exist_ok=True)

        # Remove stale feature files from any previous run
        for old in output_folder.glob("*.feature"):
            old.unlink()

        written: list[str] = []
        for index, scenario in enumerate(scenarios, start=1):
            safe_name = (
                scenario.title
                .replace(" ", "_")
                .replace("/", "_")
                .replace(":", "_")   # colon is illegal in Windows filenames
                .replace("\\", "_")
                .replace("*", "_")
                .replace("?", "_")
                .replace('"', "_")
                .replace("<", "_")
                .replace(">", "_")
                .replace("|", "_")
            )
            file_path = output_folder / f"{index:03}_{safe_name}.feature"
            file_path.write_text(scenario.gherkin, encoding="utf-8")
            print(f"Generated: {file_path}")
            written.append(str(file_path))

        return written