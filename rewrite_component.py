filename = input("Enter filename (without extension): ")
react = open(filename + ".txt", "r")

is_sd_index = input("Is this an SD index file? (y/n) ") == "y"

new_file_lines = [
    "import { ComponentProps, ConsumerSubject, DisplayComponent, FSComponent, MappedSubject, Subject, Subscribable, VNode } from '@microsoft/msfs-sdk';",
]
simvar_names = []


def write_file():
    with open(filename + ".tsx", "w") as result:
        for line in new_file_lines:
            if line.endswith("\n"):
                result.write(line)
            else:
                result.write(line + "\n")


def tab(multiplier=1):
    return "    " * multiplier


def capitalize_first_letter(string):
    return string[0].upper() + string[1:]


def generate_simvar_line(line):
    variable_name = line[line.index("[") + 1 : line.index("]")]
    simvar_names.append(variable_name)

    unit_start = line.index("', '") + 4
    simvar_unit = line[unit_start : line.find("'", unit_start)]

    type = "b" if simvar_unit.startswith("bool") else "n"

    return (
        f"{tab()}private {variable_name} = ConsumerSubject.create(this.sub.on('{variable_name}'), "
        + ("0" if type == "n" else "false")
        + ");"
    )


def handle_use_state_line(line):
    variable_name = line[line.index("const [") + 7 : line.index(",")]
    default_value = line[line.index("useState(") + 9 : line.index(")")]

    return f"{tab()}private {variable_name} = Subject.create({default_value});"


def check_if_function_exists(fn_name: str):
    for line in new_file_lines:
        if f"private {fn_name}(" in line:
            return True
    return False


def check_if_variable_exists(var_name: str):
    for line in new_file_lines:
        if f"private {var_name}: " in line or f"private {var_name} = " in line:
            return True
    return False


def get_all_props():
    reached_interface = False
    left_interface = False

    # Tuple array: (prop_name, prop_type, index_in_new_file_lines)
    props = []

    for i, line in enumerate(new_file_lines):
        left_interface = reached_interface and (":" not in line or ";" not in line)

        if reached_interface and not left_interface:
            prop_name = line.strip().split(":")[0]
            prop_type = line[line.index(":") + 1 : line.index(";")].strip()
            props.append((prop_name, prop_type, i))

        reached_interface = reached_interface or line.startswith("interface")
    return props


def prompt_for_subscribables():
    props = get_all_props()

    for prop in props:
        subscribable = input(f"Should {prop[0]} be subscribable? (y/n) ") == "y"
        if subscribable:
            new_file_lines[prop[2]] = f"{tab()}{prop[0]}: Subscribable<{prop[1]}>;"


def check_interface_for_prop(prop):
    props = get_all_props()

    for p in props:
        if p[0] == prop:
            return True
    return False


def check_if_prop_subscribable(prop: str):
    props = get_all_props()

    for p in props:
        if p[0] == prop:
            return "Subscribable" in p[1]
    return False


def replace_subject(
    variable_name: str, function_body: list[str], dependencies: list[str]
):
    i = -1
    for line in new_file_lines:
        i += 1
        if variable_name in line:
            break

    line = new_file_lines[i]

    if len(dependencies) == 1:
        function_body_processed = []
        for fn_line in function_body:
            new_line = fn_line.replace(dependencies[0], "v")
            new_line = new_line.replace(
                f"set{capitalize_first_letter(variable_name)}", "return "
            )
            function_body_processed.append(new_line)

        updated_line = (
            line[: line.index("=") + 2]
            + f"this.{dependencies[0]}.map((v) => {{ {''.join(function_body_processed)} }});"
        )

        new_file_lines[i] = updated_line
    else:
        function_body_processed = []
        for fn_line in function_body:
            new_line = new_line.replace(
                f"set{capitalize_first_letter(variable_name)}", "return "
            )
            function_body_processed.append(new_line)

        dependencies_processed = []
        for dep in dependencies:
            dependencies_processed.append(f"this.{dep}")

        updated_line = (
            line[: line.index("=") + 2]
            + f"MappedSubject.create(([{', '.join(dependencies)}]) => {{ {''.join(function_body_processed)} }}, {', '.join(dependencies_processed)})"
        )

        new_file_lines[i] = updated_line


# This function only works if the function body is a one-liner return statement
def insert_new_mapped_subject(
    variable_name: str, function_body: str, dependencies: list[str]
):
    new_mapped_subject = f"private {variable_name} = MappedSubject.create(({', '.join(dependencies)}) => ({function_body}), {', '.join([f'{get_prefix(dep)}{dep}' for dep in dependencies])})"

    line_to_find = "private subscriptions" if is_sd_index else "render(): VNode"
    for i, l in enumerate(new_file_lines):
        if line_to_find in l:
            new_file_lines.insert(i, new_mapped_subject)
            break


def get_prefix(prop_name):
    this_dot = (
        "this."
        if (
            check_if_prop_subscribable(prop_name)
            or not check_interface_for_prop(prop_name)
        )
        else ""
    )
    props_dot = (
        "props."
        if check_if_prop_subscribable(prop_name) and check_interface_for_prop(prop_name)
        else ""
    )
    return f"{this_dot}{props_dot}"


def convert_ternary_to_map(ternary: str):
    replacement = ternary

    # Now extract the comparison
    comparison = ternary.split("?")[0].strip()
    # Count how many variables the comparison has
    comparison_split = comparison.split(" ")
    variable_count = 0
    for i in comparison_split:
        if i.isalpha():
            variable_count += 1
    # If the comparison only has one variable, convert it to a map expression
    if variable_count == 1:
        variable_name = comparison_split[0]

        prefix = get_prefix(variable_name)

        # We only want to convert the ternary if it involves a subscribable
        if check_if_prop_subscribable(variable_name) or check_if_variable_exists(
            variable_name
        ):
            replacement = (
                f"{prefix}{variable_name}.map(({variable_name}) => ({ternary}))"
            )
    else:
        variable_names = []
        for i in comparison_split:
            if i.isalpha():
                variable_names.append(i)

        # We only want to convert the ternary if it involves a subscribable (this only checks if one of them is subscribable)
        variables_are_subscribables = False
        for v in variable_names:
            if check_if_prop_subscribable(v) or check_if_variable_exists(v):
                variables_are_subscribables = True
                break

        if variables_are_subscribables:
            variable_name = "".join(
                [capitalize_first_letter(v) for v in variable_names]
            )
            variable_name = variable_name[0].lower() + variable_name[1:]

            insert_new_mapped_subject(variable_name, ternary, variable_names)

            replacement = f"this.{variable_name}"

    return replacement


# Returns parsed JSX data
def parse_jsx(jsx_lines: list[str]):
    parsed_jsx = []
    element_stack = []

    def add_to_stack_or_parsed(element_tuple):
        if element_stack:
            element_stack[-1][2].append(element_tuple)
        else:
            parsed_jsx.append(element_tuple)

    for line in jsx_lines:
        stripped_line = line.strip()

        if stripped_line.startswith("</"):
            closed_element = element_stack.pop()
            if element_stack:
                element_stack[-1][2].append(closed_element)
            else:
                parsed_jsx.append(closed_element)

        elif stripped_line.startswith("<"):
            # Find the index of the tag end
            tag_end = stripped_line.rfind(">")
            # Figure out if the tag is self-closing
            is_self_closing = stripped_line[tag_end - 1] == "/"
            # Remove trailing/leading forward slash (for self-closing tags) and whitespace
            tag_content = stripped_line[1:tag_end].strip("/ ")

            tag_parts = []

            # Handle empty tags
            is_empty_tag = tag_content == ""
            if is_empty_tag:
                tag_parts = [""]

            i = -1
            for item in tag_content.split():
                # Add the element
                if len(tag_parts) == 0:
                    tag_parts.append(item)
                    i += 1
                    continue

                # Parse props as key-value pairs
                key_value = item.split("=")

                equal_sign_index = item.find("=")
                # Make sure something precedes and follows the equal sign. If not, then it's a comparison probably in a ternary
                is_not_a_comparison = (
                    equal_sign_index != -1
                    and equal_sign_index != 0
                    and equal_sign_index != len(item) - 1
                )

                if len(key_value) == 2 and is_not_a_comparison:
                    tag_parts.append(item)
                    i += 1
                else:
                    tag_parts[i] = tag_parts[i] + " " + item

            element = tag_parts[0]
            props = {}
            for part in tag_parts[1:]:
                if "=" in part:
                    prop_name, prop_value = part.split("=", 1)  # Split only once
                    props[prop_name] = prop_value

            if is_self_closing:
                add_to_stack_or_parsed((element, props, []))
            else:
                current_element = (element, props, [])
                element_stack.append(current_element)

        else:
            if element_stack:
                element_stack[-1][2].append(stripped_line)

    return parsed_jsx


def process_jsx(parsed_jsx, edit_fn):
    def edit_element(element_tuple):
        element, props, children = element_tuple
        edited_props = {}
        for prop_name, prop_value in props.items():
            new_prop_name, new_prop_value = edit_fn(element, prop_name, prop_value)
            edited_props[new_prop_name] = new_prop_value

        edited_children = [
            edit_element(child) if isinstance(child, tuple) else child
            for child in children
        ]

        props_str = " ".join([f"{key}={value}" for key, value in edited_props.items()])

        # Handle children that could potentially be dynamic (like including subscribables)
        if (
            len(children) > 0
            and isinstance(children[0], str)
            and children[0].strip().startswith("{")
            and children[0].strip().endswith("}")
        ):
            edited_children = []
            for child in children:
                child = child[1:-1]
                if "?" in child and ":" in child:
                    child = convert_ternary_to_map(child)
                    child = f"{{{child}}}"
                else:
                    child = f"{{{get_prefix(child)}{child}}}"
                edited_children.append(child)

        if edited_children:
            children_str = "\n".join(
                [
                    f"{child}" if isinstance(child, str) else edit_element(child)
                    for child in edited_children
                ]
            )
            return f"<{element} {props_str}>\n{children_str}\n</{element}>"
        else:
            return f"<{element} {props_str} />"

    edited_jsx_lines = [edit_element(element) for element in parsed_jsx]

    return edited_jsx_lines


def edit_prop(element, prop_name, prop_value):
    # Convert camel case prop names to kebab case (in normal svg elements)
    if element == element.lower():
        prop_name = "".join(
            ["-" + c.lower() if c.isupper() else c for c in prop_name]
        ).lstrip("-")

    value_is_string = prop_value.startswith('"')
    if value_is_string:
        return prop_name, prop_value

    prop_value_trimmed = prop_value[1:-1]

    # Identify if prop value is just a variable (it contains only letters)
    if prop_value_trimmed.isalpha():
        prop_value_trimmed = f"{get_prefix(prop_value_trimmed)}{prop_value_trimmed}"

    # Check if prop value is a function
    if "(" in prop_value_trimmed and ")" in prop_value_trimmed:
        function_name = prop_value_trimmed[: prop_value_trimmed.index("(")]
        parameters = prop_value_trimmed[
            prop_value_trimmed.index("(") + 1 : prop_value_trimmed.index(")")
        ].split(", ")

        # We need to check what parameters are subscribables
        subscribables = []
        for p in parameters:
            if check_if_prop_subscribable(p):
                subscribables.append(p)

        prefixed_params = ", ".join([f"{get_prefix(p)}{p}" for p in parameters])
        unedited_params = ", ".join(parameters)

        if len(subscribables) == 1:
            # We can convert it to a map expression
            prop_value_trimmed = f"{get_prefix(subscribables[0])}{subscribables[0]}.map(({subscribables[0]}) => this.{function_name}({unedited_params}))"
        elif len(subscribables) > 1:
            # We can convert it to a MappedSubject
            variable_name = "".join([capitalize_first_letter(v) for v in subscribables])
            variable_name = variable_name[0].lower() + variable_name[1:]

            insert_new_mapped_subject(
                variable_name, f"this.{function_name}({prefixed_params})", subscribables
            )

            prop_value_trimmed = f"this.{variable_name}"
        else:
            prop_value_trimmed = f"this.{function_name}({unedited_params})"

    # Identify if prop value is a ternary expression
    if "?" in prop_value_trimmed and ":" in prop_value_trimmed:
        prop_value_trimmed = convert_ternary_to_map(prop_value_trimmed)

    return prop_name, f"{{{prop_value_trimmed}}}"


subscription_pause_resume_boilerplate = [
    "",
    f"{tab()}private pause() " + "{",
    f"{tab(2)}this.subscriptions.forEach((s) => s.pause());",
    f"{tab()}" + "}",
    f"{tab()}private resume() " + "{",
    f"{tab(2)}this.subscriptions.forEach((s) => s.resume());",
    f"{tab()}" + "}",
    "",
    f"{tab()}onBeforeRender(): void " + "{",
    f"{tab(2)}super.onBeforeRender();",
    "",
    f"{tab(2)}this.props.visible.sub((v) => " + "{",
    f"{tab(3)}if (v) " + "{",
    f"{tab(4)}this.resume();",
    f"{tab(3)}" + "} else " + "{",
    f"{tab(4)}this.pause();",
    f"{tab(3)}" + "}",
    f"{tab(2)}" + "});",
    f"{tab()}" + "}",
    "",
]

paranthesis_in = 0
brackets_in = 0

added_sd_page_props_import = False

reached_declaration_line = False

is_direct_return = False
reached_return = False
paranthesis_at_return_start = 0
return_body: list[str] = []

# Function handling
is_in_function = False
paranthesis_at_function_start = 0
brackets_at_function_start = 0

# useEffect handling (similar to function handling)
is_in_use_effect = False
paranthesis_at_use_effect_start = 0
brackets_at_use_effect_start = 0
use_effect_body: list[str] = []


def handle_reached_return():
    if is_sd_index:
        new_file_lines.append(f"{tab()}private subscriptions = [")
        for simvar_name in simvar_names:
            new_file_lines.append(f"{tab(2)}this.{simvar_name},")
        new_file_lines.append(f"{tab()}];")
        new_file_lines.extend(subscription_pause_resume_boilerplate)

    new_file_lines.append(f"{tab()}render(): VNode " + "{")

    props = get_all_props()
    static_props = [p[0] for p in props if "Subscribable" not in p[1]]

    if static_props:
        new_file_lines.append(
            f"{tab(2)}const " + "{ " + ", ".join(static_props) + " } = this.props;"
        )
        new_file_lines.append("")

    new_file_lines.append(f"{tab(2)}return (")


for line in react.readlines():
    paranthesis_in += line.count("(")
    paranthesis_in -= line.count(")")
    brackets_in += line.count("{")
    brackets_in -= line.count("}")

    is_import_line = line.startswith("import")

    # Ignore react import and hook imports
    if is_import_line and ("use" in line or "React" in line):
        continue

    if is_import_line:
        if "Container" in line:
            new_file_lines.append(
                "import { Container } from '@instruments/common-msfs-avionics/Container';"
            )
        else:
            new_file_lines.append(line)
        continue

    if is_sd_index and not reached_declaration_line and not added_sd_page_props_import:
        new_file_lines.append("import { SDPageProps } from '..';")
        added_sd_page_props_import = True

    # Convert type interfaces
    if line.startswith("interface"):
        extends_something = "extends" in line
        export = "export" in line
        if not extends_something:
            interface_name = line.split(" ")[1]
            new_file_lines.append(
                ("export " if export else "")
                + f"interface {interface_name} extends ComponentProps "
                + "{"
            )
            continue
        new_file_lines.append(line)
        continue

    # Convert component declaration
    if line.startswith("export const"):
        # Cheap way to check if we've passed the interface I guess
        prompt_for_subscribables()

        reached_declaration_line = True
        is_direct_return = line.endswith("(\n")

        component_name = line.split(" ")[2].replace(":", "")
        has_props_interface = line.find("FC<") != -1
        props_interface_name = (
            "SDPageProps"
            if not has_props_interface
            else line[line.find("FC<") + 3 : line.find(">")]
        )

        # Write the component class declaration
        new_file_lines.append(
            f"export class {component_name} extends DisplayComponent<{props_interface_name}> "
            + "{"
        )

        # Add the simvar subscriber
        if is_sd_index:
            new_file_lines.append(
                f"{tab()}private sub = this.props.bus.getSubscriber<{component_name}SimVars>();"
            )
            new_file_lines.append("")

        if is_direct_return:
            reached_return = True
            paranthesis_at_return_start = paranthesis_in
            handle_reached_return()

        continue

    # Convert simvar lines
    if "useSimVar" in line:
        new_file_lines.append(generate_simvar_line(line))
        continue

    # Convert useState lines
    if "useState" in line:
        new_file_lines.append(handle_use_state_line(line))
        continue

    # Convert misc functions
    if "const" in line and "=>" in line:
        is_in_function = True
        paranthesis_at_function_start = paranthesis_in
        brackets_at_function_start = brackets_in

        function_name = line[line.index("const ") + 6 : line.index("=")].strip()
        parameters = line[line.index("(") + 1 : line.index(")")]

        new_file_lines.append(f"{tab()}private {function_name}({parameters}) " + "{")

        # Check if the function is a one-liner (which also means it's a direct return)
        if line.endswith(";\n"):
            function_body = line[line.index("=>") + 2 : line.index(";")]
            new_file_lines.append(f"{tab(2)}return {function_body};")
            new_file_lines.append(f"{tab()}" + "};")
            is_in_function = False

        continue
    if is_in_function:
        if (
            paranthesis_in < paranthesis_at_function_start
            or brackets_in < brackets_at_function_start
        ):
            new_file_lines.append(f"{tab()}" + "};")
            is_in_function = False
            continue
        new_file_lines.append(line)
        continue

    # Convert useEffect to map the Subscribable or use a MappedSubject
    if "useEffect" in line:
        is_in_use_effect = True
        paranthesis_at_use_effect_start = paranthesis_in
        brackets_at_use_effect_start = brackets_in

        continue
    if is_in_use_effect:
        if (
            paranthesis_in < paranthesis_at_use_effect_start
            or brackets_in < brackets_at_use_effect_start
        ):
            is_in_use_effect = False

            # Now we extract the dependencies
            dependencies = line[line.index("[") + 1 : line.index("]")].split(", ")

            variable_name = "idk"
            for use_effect_line in use_effect_body:
                if "set" in use_effect_line:
                    variable_start = use_effect_line.index("set") + 3
                    variable_name = use_effect_line[
                        variable_start : use_effect_line.find("(", variable_start)
                    ]
                    variable_name = variable_name[0].lower() + variable_name[1:]
                    break

            replace_subject(variable_name, use_effect_body, dependencies)
            use_effect_body = []

            continue
        use_effect_body.append(line)
        continue

    # Handle pausing/resuming subscriptions (only for SD index files)
    if "return (" in line and not reached_return:
        reached_return = True
        paranthesis_at_return_start = paranthesis_in
        handle_reached_return()
        continue

    if reached_return:
        if paranthesis_in < paranthesis_at_return_start:
            new_file_lines.extend(process_jsx(parse_jsx(return_body), edit_prop))

            reached_return = False
            new_file_lines.append(f"{tab(2)});")
            new_file_lines.append(f"{tab()}" + "}")
            new_file_lines.append("}")
            continue
        return_body.append(line)
        continue

    # Check if we've reached the end of the first component in the file, because this script can only handle one at a time
    if reached_declaration_line and paranthesis_in == 0 and brackets_in == 0:
        break

    # Handle the rest of the file
    new_file_lines.append(line)

write_file()
react.close()
