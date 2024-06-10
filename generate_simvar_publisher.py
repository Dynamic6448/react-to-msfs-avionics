newFileLines = [
    "import { EventBus, SimVarDefinition, SimVarPublisher, SimVarValueType } from '@microsoft/msfs-sdk';",
    "",
    "export interface PageSimVars {",
    "}",
    "",
    "export enum PageVars {",
    "}",
    "",
    "export class PageSimVarPublisher extends SimVarPublisher<PageSimVars> {",
    "    private static simVars = new Map<keyof PageSimVars, SimVarDefinition>([",
    "    ]);",
    "",
    "    public constructor(bus: EventBus) {",
    "        super(PageSimVarPublisher.simVars, bus);",
    "    }",
    "}",
]

sim_vars_start_index = 3
vars_start_index = 6
map_start_index = 10

def camel_case_to_snake_case(string):
    return ''.join(['_' + c.lower() if c.isupper() else c for c in string]).lstrip('_').upper()
def capitalize_first_letter(string):
    return string[0].upper() + string[1:]
def capitalize_all_words(string):
    return ''.join([capitalize_first_letter(word) for word in string.split()])

with open("react.txt", "r") as react:
    i = 0
    for line in react.readlines():
        if len(line.strip()) == 0:
            newFileLines.insert(sim_vars_start_index + i, "")
            newFileLines.insert(vars_start_index + i * 2 + 1, "")
            newFileLines.insert(map_start_index + i * 3 + 2, "")
            i += 1
            continue

        variable_name = line[line.index("[") + 1 : line.index("]")]

        simvar_name = line[line.index("('") + 2 : line.index("',")]

        unit_start = line.index("', '") + 4
        simvar_unit = line[unit_start : line.find("'", unit_start)]

        type = "number"

        if simvar_unit.startswith("bool"):
            # make sure it's bool not boolean
            simvar_unit = "bool"
            type = "boolean"

        variable_snake = camel_case_to_snake_case(variable_name)
        simvar_value_type = capitalize_all_words(simvar_unit)
        if len(simvar_value_type) <= 3:
            simvar_value_type = simvar_value_type.upper()

        newFileLines.insert(sim_vars_start_index + i, f"    {variable_name}: {type};")
        newFileLines.insert(vars_start_index + i * 2 + 1, f"    {variable_snake} = '{simvar_name}',")
        newFileLines.insert(map_start_index + i * 3 + 2, f"        ['{variable_name}', " + "{" + f" name: PageVars.{variable_snake}, type: SimVarValueType.{simvar_value_type} " + "}],")

        i += 1

with open("PageSimVarPublisher.ts", "w") as result:
    for line in newFileLines:
        result.write(line + "\n")
