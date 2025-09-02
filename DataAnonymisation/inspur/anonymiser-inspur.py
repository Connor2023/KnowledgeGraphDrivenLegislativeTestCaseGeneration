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

    def check(s: str) -> str | dict:
        # handle figures (multimodal)
        if s[:len("Figure ")] == "Figure ":
            return {
                "mode": "Figure",
                "id": s.split()[1],
                "name": " ".join(s.split()[2:]),
                "link": None
            }

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
        if "SMSRS" in source:
            info = {
                "id": id_num,
                "name": name,
                "chapters": {}
            }

            level_names = [None] * 3
            curr_chapter = []
            curr_chapter_num = 1
            curr_feature = {}
            level_stack = []
            first = True

            with open(source, "r") as file:
                for line in file:
                    if line.strip() != "":
                        # Deal with if it's a heading first
                        s = line.strip()
                        if s[0].isdigit():
                            level_stack.append(s)
                        # deal with if it is content (requirement description/image)
                        elif s not in Anonymiser.REDUNDANT_LINES and any([not s[i].isdigit() for i in range(len(s))]):
                            if len(level_stack) > 0:
                                if len(level_stack) == 3 and curr_chapter:
                                    if "description" in curr_feature or "multimodal" in curr_feature:
                                        curr_chapter.append(curr_feature)
                                    info["chapters"][curr_chapter_num] = curr_chapter
                                    curr_chapter = []
                                    curr_chapter_num += 1
                                elif len(level_stack) <= 2 and "description" in curr_feature or "multimodal" in curr_feature:
                                    curr_chapter.append(curr_feature)

                                # update level names from stack
                                if first:
                                    for i in range(1, 1 - len(level_stack), -1):
                                        level_names[i] = level_stack.pop()
                                    first = False
                                else:
                                    for i in range(2, 2 - len(level_stack), -1):
                                        level_names[i] = level_stack.pop()

                                curr_feature = {
                                    "category": level_names[0],
                                    "subcategory": level_names[1],
                                    "requirement": level_names[2]
                                }

                            if "description" not in curr_feature:
                                curr_feature["description"] = [Anonymiser.check(s)]
                            else:
                                curr_feature["description"].append(Anonymiser.check(s))
            
            if curr_chapter:
                if "description" in curr_feature or "multimodal" in curr_feature:
                    curr_chapter.append(curr_feature)
                    curr_feature = {}
                info["chapters"][curr_chapter_num] = curr_chapter
        else:
            info = {
                "id": id_num,
                "name": name,
                "chapters": {}
            }

            level_names = [None] * 10
            last_id = None
            curr_chapter = []
            curr_chapter_num = 1
            curr_feature = {}

            with open(source, "r") as file:
                for line in file:
                    if line.strip() != "":
                        # Deal with if it's a heading first
                        s = line.strip()
                        if len(s) > len("Chapter") and s[:len("Chapter")] == "Chapter":
                            if curr_chapter:
                                if "description" in curr_feature or "multimodal" in curr_feature:
                                    curr_chapter.append(curr_feature)
                                    curr_feature = {}
                                info["chapters"][curr_chapter_num] = curr_chapter
                            curr_chapter = []
                            curr_chapter_num += 1
                        elif len(s) >= 3 and s[0].isdigit() and s[1] == "." and s[2].isdigit():
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
                                if "CMSRS" in source:
                                    if i <= level:
                                        curr_feature[level_titles[i - 2]] = level_names[i]
                                elif "PRSRS" in source:
                                    j = i - 1
                                    if j <= level:
                                        curr_feature[level_titles[i - 2]] = level_names[j]
                        elif len(s) >= 3 and s[0].isdigit() and s[1] == "." and s[2] == " ":
                            level = 1
                            level_name = s[3:]
                            level_names[level] = level_name

                        # deal with if it is content (requirement description/image)
                        elif s not in Anonymiser.REDUNDANT_LINES and any([not s[i].isdigit() for i in range(len(s))]):
                            if "description" not in curr_feature:
                                curr_feature["description"] = [Anonymiser.check(s)]
                            else:
                                if isinstance(curr_feature["description"][-1], str) and isinstance(Anonymiser.check(s), str) and curr_feature["description"][-1][-1] not in ".;:":
                                    curr_feature["description"][-1] = curr_feature["description"][-1] + " " + Anonymiser.check(s)
                                else:
                                    curr_feature["description"].append(Anonymiser.check(s))
            
            if curr_chapter:
                if "description" in curr_feature or "multimodal" in curr_feature:
                    curr_chapter.append(curr_feature)
                    curr_feature = {}
                info["chapters"][curr_chapter_num] = curr_chapter

        with open(target, "w") as file:
            json.dump(info, file, indent=4)

        print("Data anonymised!")


sources = ["CMSRS", "PRSRS", "SMSRS"]
id_nums = [3, 2, 1]
names = [
    "Case Management System Project User Requirements", 
    "Patient Registration System Requirements Specification", 
    "Safety Monitoring System Requirements Specification"
    ]

for s, i, n in zip(sources, id_nums, names):
    Anonymiser.anonymise("./input/" + s + ".txt", "./output/anonymised_" + s + ".json", i, n)