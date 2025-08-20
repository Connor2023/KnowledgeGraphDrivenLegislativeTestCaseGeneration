import json

class Anonymiser():
    LINK_PLACEHOLDER = "[Internal Requirement Reference]"

    ID_MAPPING = {
        "EDAMOO-16515": "REQ-001",
        "EDAMOO-16640": "REQ-002",
        "EDAMOO-16712": "REQ-003",
        "EDAMOO-18306": "REQ-004",
        "EDAMOO-17949": "REQ-005",
        "EDAMOO-17940": "REQ-006",
        "EDAMOO-17804": "REQ-007",
        "EDAMOO-17708": "REQ-008",
        "EDAMOO-16974": "REQ-009",
        "EDAMOO-16795": "REQ-010",
        "EDAMOO-16715": "REQ-011",
        "EDAMOO-16725": "REQ-012",
        "EDAMOO-16767": "REQ-013",
        "EDAMOO-16791": "REQ-014",
        "EDAMOO-16796": "REQ-015",
        "EDAMOO-16800": "REQ-016",
    }
    GEN_ID_CURR = 17
    GEN_ID_PREFIX = "REQ-"

    GENERALISATIONS = {
        "Monash Standard": "Standard Course",
        "Monash Project": "Project-Based",
        "VLE Administrator": "Platform Administrator",
        "OES Administrator": "Course Administrator",
        "Chief Examiner": "Lead Academic",
        # added terms
        "Monash Coursework": "Standard Coursework",
        "STANDARD MONASH": "COURSE STANDARD",
        "standard Monash": "course standard",
        "Monash Australian": "[University]",
        "Monash blue": "[Colour]",
        "Monash": "[University]",
        "Moodle": "learning system",
        "EDAMOO-17147": "[Internal User Story]",            # These two IDs were only referenced once each within other user stories
        "EDAMOO-17705": "[Internal User Story]",
    }

    ID = 'ID'

    def generate_new_id(prev: str) -> str:
        new_id = Anonymiser.GEN_ID_PREFIX + "0" * (3 - len(str(Anonymiser.GEN_ID_CURR))) + str(Anonymiser.GEN_ID_CURR)
        Anonymiser.GEN_ID_CURR += 1

        Anonymiser.ID_MAPPING[prev] = new_id
        return new_id

    def check(s: str) -> str:
        # handle specified terms
        for old, new in Anonymiser.GENERALISATIONS.items():
            s = s.replace(old, new)

        # handle website links
        new = []
        for word in s.split():
            if word.startswith("https"):
                if word[-12:-6] == "EDAMOO":
                    new.append(Anonymiser.ID_MAPPING[word[-12:]])
                else:
                    new.append(Anonymiser.LINK_PLACEHOLDER)
            elif word.startswith("spreadsheet|https"):
                new.append("spreadsheet|" + Anonymiser.LINK_PLACEHOLDER + "]")
            elif word.startswith("(https"):
                new.append("( " + Anonymiser.LINK_PLACEHOLDER)
            else:
                new.append(word)

        s = ' '.join(new)

        # replace EDAMOO references that are not within URLs
        for old, new in Anonymiser.ID_MAPPING.items():
            s = s.replace(old, new)

        return s
    
    def check_list(lst: list) -> list:
        for i in range(len(lst)):
            if isinstance(lst[i], dict):
                Anonymiser.check_dict(lst[i])
            else:
                lst[i] = Anonymiser.check(lst[i])

    def check_dict(dct: dict) -> dict:
        for k, i in dct.items():
            dct[k] = Anonymiser.check(i)

    def anonymise(source: str, target: str) -> None:
        with open(source, "r") as file:
            info = json.load(file)

            # get id mappings first
            for story in info:
                item = story[Anonymiser.ID]
                if item in Anonymiser.ID_MAPPING:
                    story[Anonymiser.ID] = Anonymiser.ID_MAPPING[item]
                else:
                    story[Anonymiser.ID] = Anonymiser.generate_new_id(item)

            # can rework links between user stories now
            for story in info:
                for key, item in story.items():
                    if key == Anonymiser.ID:
                        continue
                    
                    elif isinstance(item, list):
                        Anonymiser.check_list(item)

                    elif isinstance(item, dict):
                        Anonymiser.check_dict(item)

        info.append(Anonymiser.ID_MAPPING)

        with open(target, "w") as file:
            json.dump(info, file, indent=4)


        print("Data anonymised!")


source = "input/checked_data.json"
target = "output/anonymised_checked_data.json"

Anonymiser.anonymise(source, target)