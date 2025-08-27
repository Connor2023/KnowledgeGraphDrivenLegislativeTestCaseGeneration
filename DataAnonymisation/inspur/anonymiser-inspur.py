"""
This file anonymises a given .txt file (obtained by passing a PDF of requirements through a parser like https://pdfkit.com)
Then outputs this information to a .json file
"""


import json

class Anonymiser():
    LINK_PLACEHOLDER = lambda x: "[" + x + " Resource]" # x is External/Internal

    GENERALISATIONS = {
        "Tianyancha": "T Person"
    }

    REDUNDANT_LINES = {"Machine Translated by Google", "Machine Translated by Google"}

    def check(s: str) -> str:
        # handle specified terms
        for old, new in Anonymiser.GENERALISATIONS.items():
            s = s.replace(old, new)

        # handle website links
        new = []
        for word in s.split():
            if word.startswith("https"):
                new.append(Anonymiser.LINK_PLACEHOLDER("External"))
            else:
                new.append(word)

        s = ' '.join(new)

        return s

    def anonymise(source: str, target: str, id_num: int, name: str) -> None:
        info = {
            "id": id_num,
            "name": name,
            "chapters": {}
        }

        level_names = [None] * 10
        last_id = None
        curr_chapter = []
        curr_chapter_num = None
        curr_feature = {}

        with open(source, "r") as file:
            for line in file:
                if line.strip() != "":
                    s = line.strip()
                    if s[:len("Chapter")] == "Chapter":
                        if curr_chapter:
                            info["chapters"][curr_chapter_num] = curr_chapter
                        curr_chapter = []
                        curr_chapter_num = int(s[len("Chapter") + 1])
                    elif s[0].isdigit() and s[1] == "." and s[2].isdigit():
                        if "description" in curr_feature or "multimodal" in curr_feature:
                            curr_chapter.append(curr_feature)
                        level = len(s.split()[0].split("."))
                        level_name = s[len(s.split()[0]) + 1:]
                        level_names[level] = level_name
                        last_id = s[:len(s.split()[0])]

                        curr_feature = {
                            "id": last_id
                        }
                        level_titles = ["requirement", "feature", "subfeature"]
                        for i in range(2, 5):
                            if i <= level:
                                curr_feature[level_titles[i - 2]] = level_names[i]

                    elif s not in Anonymiser.REDUNDANT_LINES:
                        if "description" not in curr_feature:
                            curr_feature["description"] = [Anonymiser.check(s)]
                        else:
                            if curr_feature["description"][-1][-1] not in ".;:":
                                curr_feature["description"][-1] = curr_feature["description"][-1] + " " + Anonymiser.check(s)
                            else:
                                curr_feature["description"].append(Anonymiser.check(s))
                    

        with open(target, "w") as file:
            json.dump(info, file, indent=4)

        print("Data anonymised!")


sources = ["CMSRS.txt"]
id_nums = [3]
names = ["Case Management System Project User Requirements"]

for s, i, n in zip(sources, id_nums, names):
    Anonymiser.anonymise("./input/" + s, "./output/anonymised_" + s[:-4] + ".json", i, n)