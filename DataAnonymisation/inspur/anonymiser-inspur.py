import json

class Anonymiser():
    LINK_PLACEHOLDER = lambda x: "[" + x + " Resource]" # x is External/Internal

    GENERALISATIONS = {
        "Tianyancha": "T Person"
    }

    DELETIONS = {"Machine Translated by Google", "Machine Translated by Google"}

    def check(s: str) -> str:
        # handle specified terms
        for old, new in Anonymiser.GENERALISATIONS.items():
            s = s.replace(old, new)

        # handle website links
        new = []
        for word in s.split():
            if word.startswith("https"):
                new.append(Anonymiser.LINK_PLACEHOLDER("External"))

        s = ' '.join(new)

        return s

    def anonymise(source: str, target: str) -> None:
        info = {}

        with open(source, "r") as file:
            pass

        with open(target, "w") as file:
            json.dump(info, file, indent=4)

        print("Data anonymised!")


sources = "CMSRS.txt"
targets = "anonymised_CMSRS.json"

for src, tgt in zip(sources, targets):
    Anonymiser.anonymise("input/" + src, "output/" + tgt)