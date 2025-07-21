md_input = """
This is a promptchain md input format. A structure that let's users specify a reproducable list of prompts. It needs a more readable md format syntax that is still python parsable + html and js safe(won't conflict with the syntax of those languages)
metadata is optional (except for the first promptstep). Multiple context variables are allowed.
variables must start with "- " and be on the same line as a colon ":". The variable is set to the text after the colon, up to the next line starting with "- " or the next new section. 
each section is separated by ###. Text on the same line as the ### is the section name. You can name the section anything you want. To reference the section name, use the varized version of the section name "varized_section_3_prompt_name", or reference the section number "3", or reference the section name using prompt then section number "prompt_3"
Algo to varize a string: lowercase the string, replace spaces with underscores. This is the varized version of the string.
If a promptstep section has multiple completions, add a number to the end of the output_var_name. The first completion is just the output_var_name or output_var_name.1, the second is the output_var_name.2, etc. An "all" variable contains all the completions -> output_var_name.all are the outputs of all completions appended together.

Allow for comments via ## for single line. (comments are ignored first in the parsing)
To add a comment (a line that is ignored by the parser), include "##" in the line and the rest of the line will be ignored by the parser. Comments are useful for adding notes to the md file that are not parsed by the parser. Comments are never seen by the model.
prompt variables are surrounded by [[ ]]. Each promptstep output is referenced as a variable [[promptstep_number]]
internal [[ ]] whitespace is ignored
syntax is designed to be readable, easy to write, and easy to parse
leading/trailing whitespace is ignored
handle unknown variables by raising an error
to validate the variables at each step, make a dictionary of the variables. We'll slowly add to it as we go through the steps. At each step, we'll check if the step variables are in the dictionary. If not, we'll raise an error (var ___ doesn't exist at this promptstep. Current variables ___). If they are, we'll add the step output to the dictionary. This process is very similar to the promptchain execution process
each section is separated by ###. The first section is always the variables section and non-variable text will be ignored. The rest are promptsteps (with optional LLM metadata)

implimentation:
seperate md into variables, and list of (promptstep, metadata) pairs

example valid md input:
## Variables (note that this line is a comment and will be ignored by the parser)
Text here is ignored by the parser as well (but just because it's in the variables section, in any other step this text would be parsed as a prompt)
## can have as many variables as you want
- context:
an entertaining political email Newsletter
- key_message_1: we are writing a political newsletter for the Thanksgiving season
## ect...

### Prompt 1
Pitch [[ context ]] piece by first ideating a theme and then crafting the ideal audience avatar attributes. Be Very Concise

## Metadata (the model key MUST be present for the first promptstep, it's optional for the rest)
## all other keys tweak the model settings
- model: openai/gpt-3.5-turbo ## or openai/gpt-4o or anthropic/claude-3-haiku or meta-llama/llama-3-70b-instruct:nitro 
- temperature: 0
- completions: 1

### Draft the piece
[[1]]


Draft [[context]] piece. Address the reader as "[reader]"
## note that there is no metadata section for this promptstep. The model settings are inherited from the first promptstep

### get subject lines
## note that this prompt has multiple input variables. They will be filled in by the previous promptstep results
Audience avatar:
[[1]]

[[draft_the_piece]]

Ideate a list of concise subject lines that would appeal to the above audience avatar

## Metadata
- model: openai/gpt-3.5-turbo-16k ## goodest model for talking about subject lines
- temperature: 1
"""

md_input_ ="""
## Variables
- context:
an entertaining political email Newsletter

### Prompt 1
Pitch [[ context ]] piece by first ideating a theme and then crafting the ideal audience avatar attributes. Be Very Concise

## Metadata
- model: openai/gpt-3.5-turbo ## or openai/gpt-4o or anthropic/claude-3-haiku or meta-llama/llama-3-70b-instruct:nitro 
- temperature: 0
- completions: 1

###
[[1]]


Draft [[context]] piece. Address the reader as "[reader]"

### get subject lines
Audience avatar:
[[1]]

[[2]]

Ideate a list of concise subject lines that would appeal to the above audience avatar

## Metadata
- model: openai/gpt-3.5-turbo-16k ## goodest model for talking about subject lines
- completions: 1
- temperature: 1

### Copywriter character persona
Ideate the ideal copywriter character persona. Someone hardworking, creative, and worldly.

- completions: 3

### select the best writer
[[copywriter_character_persona.2]]


"""


md_input_test ="""
## Variables
- context:
an entertaining political email Newsletter

### Prompt 1
Pitch [[ context ]] piece by first ideating a theme and then crafting the ideal audience avatar attributes. Be Very Concise

## Metadata
- model: openai/gpt-3.5-turbo ## or openai/gpt-4o or anthropic/claude-3-haiku or meta-llama/llama-3-70b-instruct:nitro 
- temperature: 0
- completions: 1

### Draft the piece
[[1]]


Draft [[context]] piece. Address the reader as "[reader]"

### get subject lines
Audience avatar:
[[1]]

[[2]]

Ideate a list of concise subject lines that would appeal to the above audience avatar. Return a Python List of the subject lines.

## Metadata
- model: openai/gpt-3.5-turbo ## goodest model for talking about subject lines
- list: True
- completions: 1
- temperature: 1

### remove colon from subject lines
[[get_subject_lines.each]]

remove the colon (if any) from the subject line. Else return the subject line as is. Don't discuss ANYTHING, just remove the colon.


### Copywriter character persona
Ideate the ideal copywriter character persona. Someone hardworking, creative, and worldly.

- completions: 3

### select the best writer
[[copywriter_character_persona.1]]

[[copywriter_character_persona.all]]

Select the best 2 writers from the list of copywriter character personas.
- select: 2 ## either an integer number of selections or True to let the model decide


"""

# Expected output
"""
{
    "variables": {
    "context": "an entertaining political email Newsletter"
    },
    "prompt_chain": [
        {
            "prompt": "Pitch [[context]] piece by first ideating a theme and then crafting the ideal audience avatar attributes. Be Very Concise",
            "metadata": {
                "model": "openai/gpt-3.5-turbo",
                "temperature": 0,
                "completions": 1,
                "scoring_prompt": ""
            }
        },
        {
            "prompt": "[[1]]\n\n\nDraft [[context]] piece. Address the reader as "[reader]"",
            "metadata": {
                "model": "openai/gpt-3.5-turbo",
                "temperature": 0,
                "completions": 1,
                "scoring_prompt": ""
            }
        },
        {
            "prompt": "Audience avatar:\n[[1]]\n\n[[2]]\n\n\nIdeate a list of concise subject lines that would appeal to the above audience avatar",
            "metadata": {
                "model": "openai/gpt-3.5-turbo",
                "temperature": 1,
                "completions": 1,
                "scoring_prompt": ""
            }
        }
    ]
}
"""



md_input_ ="""## Variables
- context:
an entertaining political email Newsletter

### Prompt 1
Pitch [[ context ]] piece by first ideating a theme and then crafting the ideal audience avatar attributes. Be Very Concise

## Metadata
- model: openai/gpt-3.5-turbo ## or openai/gpt-4o or anthropic/claude-3-haiku or meta-llama/llama-3-70b-instruct:nitro 
- temperature: 0
- completions: 1

###
[[1]]


Draft [[context]] piece. Address the reader as "[reader]"
<!--  
### get subject lines
Audience avatar:
[[1]]

[[2]]

Ideate a list of concise subject lines that would appeal to the above audience avatar
## Metadata
- model: openai/gpt-3.5-turbo-16k ## goodest model for talking about subject lines
- completions: 1
- temperature: 1

### remove colon from subject lines
[[get_subject_lines.each]]

remove the colon (if any) from the subject line. Else return the subject line as is. Don't discuss ANYTHING, just remove the colon.

### batch remove colon from subject lines
[[get_subject_lines.each.2]]

remove the colon (if any) from the subject line. Else return the subject line as is. Don't discuss ANYTHING, just remove the colon.
-->
### Copywriter character persona
Ideate the ideal copywriter character persona. Someone hardworking, creative, and worldly.

- completions: 3

### select the best writer
[[copywriter_character_persona.all]]

Select the best 2 writers from the list of copywriter character personas.
- list: True

"""


import json, copy, time
from openrouter_engine import validate_parameters


class PromptChainParser:
    def __init__(self, separator="###"):
        self.separator = separator
        # each prompt chain step is structured in the following way:
        """
        {
            "count": 1,
            "name": "Prompt 1",
            "prompt": "Pitch [[context]] piece by first ideating a theme and then crafting the ideal audience avatar attributes. Be Very Concise",
            "prompt_var_dependancies": ["context"],
            "metadata": {
                "model": "openai/gpt-3.5-turbo",
                "temperature": 0,
                "completions": 1,
                "scoring_prompt": ""
            },
            "output_var_name": ["1", "prompt_1"],
        }
        """

    def md_promptchain_parser(self, md_input, models=None, pr=False):
        # import code; code.interact(local={**globals(), **locals()})
        # print(md_input)
        if not isinstance(md_input, str):
            raise TypeError("md_input must be a string")
        md_input = "\n" + md_input
        # clean all <!-- --> comments
        def remove_comments(text):
            start_index = text.find("<!--")
            while start_index != -1:
                end_index = text.find("-->", start_index)
                if end_index == -1:
                    raise ValueError("Unmatched <!-- in the prompt")
                text = text[:start_index] + text[end_index+3:]
                start_index = text.find("<!--")
            return text
        md_input = remove_comments(md_input)
        # split md_input into variables and promptsteps sections via the separator
        sections = md_input.split(self.separator)
        # first_section = sections[0]
        # # put the seperator back into each section (except the first one)
        # sections = first_section + [self.separator + section for section in sections[1:]]
        variables_check = {}  # needed for variable dependency check, itterating through the promptsteps
        variables = {}
        prompt_chain = []
        default_model_settings = {}
        # parse the variables section
        for idx, section in enumerate(sections):
            if idx == 0:
                variables_section = self.parse_variables_from_text(section)
                # remove prompt key value from variables_section
                variables_section.pop("prompt", None)
                variables_section.pop("name")
                variables = copy.deepcopy(variables_section)
                variables_check = copy.deepcopy(variables_section)
                # import code; code.interact(local={**globals(), - completions: **locals()})
            else:
                try:
                    section_data = self.parse_variables_from_text(section)
                    model_settings = {k: v for k, v in section_data.items() if k != "prompt" and k != "name"}
                    # convert model settings values to logical types
                    for k, v in model_settings.items():
                        if v.isdigit():
                            model_settings[k] = int(v)
                        elif "." in v and v.replace(".", "").isdigit():
                            model_settings[k] = float(v)
                    if pr: 
                        print(json.dumps(section_data, indent=4))
                        print(json.dumps(model_settings, indent=4))
                    # import code; code.interact(local={**globals(), **locals()})
                    if idx == 1: 
                        # drop all keys that are not model or completions
                        default_model_settings = {k: v for k, v in model_settings.items() if k == "model" or k == "temperature"}
                        if "completions" not in default_model_settings.keys():
                            default_model_settings["completions"] = 1
                    if "model" not in model_settings.keys() and idx == 1:
                        raise ValueError(f"First prompt MUST have a 'model' setting like so\n\n- model: anthropic/claude-3-haiku")
                    elif "model" not in model_settings.keys() and idx > 1:
                        # add the new settings to the default settings, if there are conflicts, the new settings will overwrite the default settings
                        model_settings = {**default_model_settings, **model_settings}

                    if models:
                        self.model_check(model_settings.get("model"), models)
                    # TODO: check model existance in openrouter's model list
                    # verify model settings
                    model_settings = validate_parameters(**model_settings, keep_extra_keys=True)
                    section_data["count"] = idx
                    if section_data["name"] == "":
                        section_data["name"] = f"Prompt {idx}"
                    # raise error if the prompt is empty
                    if section_data["prompt"].strip() == "":
                        raise ValueError(f"Prompt {idx} is empty")
                    # find prompt variables (surrounded by [[ ]])
                    prompt_variables = self.find_prompt_variables(section_data["prompt"])
                    if pr: print(prompt_variables)
                    # are_prompt_variable_dependencies_met
                    for var in prompt_variables:
                        var = self.handle_variably_named_vars(var)
                        if var not in variables_check.keys():
                            raise ValueError(f'variable "{var}" won\'t exist at this promptstep. Current usable variables {variables_check.keys()}')
                    section_data["prompt_var_dependancies"] = prompt_variables
                    if pr: print(self.promptstep_var_check(variables_check, section_data))
                    section_data["metadata"] = model_settings
                    varized_name = self.varize(section_data["name"])
                    output_var_name = [str(idx), varized_name]
                    if "prompt_" + str(idx) not in output_var_name:
                        output_var_name.append("prompt_" + str(idx))
                    # handle mutiple completions by adding a number to each output_var_name element
                    new_output_var_name = []
                    for var in output_var_name:
                        new_output_var_name.append(var)
                        # add to variables_check for later promptsteps
                        variables_check[var] = section_data["prompt"]
                        # make a name for each completion and map the output to that name
                        for i in range(model_settings.get("completions", 1)):
                            new_output_var_name.append(f"{var}.{i+1}")
                            variables_check[f"{var}.{i+1}"] = f"{section_data['prompt']} completion {i}"
                        # add an "all" variable that contains all the completions
                        # b/c .1 and just blank are the first completion
                        new_output_var_name.append(f"{var}.all")
                        variables_check[f"{var}.all"] = f"{section_data['prompt']} all completions"
                        # likewise add an "each" variable that contains each completion
                        # like .all but forks the prompt for each list element and then appends the completions together at the end of the promptstep
                        new_output_var_name.append(f"{var}.each")
                        variables_check[f"{var}.each"] = f"{section_data['prompt']} each completion"


                        # # similar to .each add an "every_n" variable that forks the prompt every n completions. Each fork will have at most n completions. n is an integer between 1 and the number of completions
                        # for i in range(1, model_settings.get("completions", 1)+1):
                        #     new_output_var_name.append(f"{var}.each{i}")
                        #     variables_check[f"{var}.each{i}"] = f"{section_data['prompt']} every {i} completions"
                        
                    # TODO: pass any additional variables to the variables_check

                    section_data["output_var_name"] = new_output_var_name
                    prompt_chain.append(section_data)
                except ValueError as e:
                    raise ValueError(f"Chain Validation Error in prompt step {idx}: {e}")
        self.promptchain_var_dependency_check(variables_check, prompt_chain)
        return {"variables": variables, "promptchain": prompt_chain} 
    
    def model_check(self, model: str, models: dict):
        # check if the model is in the models dictionary keys
        if model not in models.keys():
            raise ValueError(f"Model {model} not found in available models")
        
    
    def find_runnable_steps(self, variables, promptchain):
        # find all promptchain steps that have their prompt_var_dependancies in the variables
        runnable_steps = []
        for promptstep in promptchain:
            if self.promptstep_var_check(variables, promptstep):
                runnable_steps.append(promptstep)
        return runnable_steps
    

    def handle_variably_named_vars(self, var):
        if "." in var and ".each" in var:
            var = var.split(".")[0] + ".each"
        return var
    
    
    def fill_promptstep_with_variables(self, variables, promptstep, separator="\n\n"):
        # replace all prompt variables in the prompt with the variables
        # variables in the prompt are surrounded by [[ ]] and are always varized 
        # they might have whitespace around them
        # typically is run after a promptstep_var_check

        # only allow 1 .each variable per promptstep
        dot_each_count = 0
        for var in promptstep["prompt_var_dependancies"]:
            if ".each" in var:
                dot_each_count += 1
        if dot_each_count > 1:
            raise ValueError(f"Only one .each variable is currently allowed per promptstep prompt. Not sure how to handle multiple .each vars. Let Barrett know the behavior you expected from using multiple .each variables with PromptChaining(if this was intentional). {dot_each_count} were found in promptstep {promptstep['count']} {promptstep['name']}\n\n{promptstep['prompt']}")
        
        
        def insert_variable(key, value, prompt_):
            prompt = copy.deepcopy(prompt_)
            #if var in prompt:
            key_start_index = prompt.find(key)
            # find previous [[
            start_index = prompt.rfind("[[", 0, key_start_index)
            # find the next ]]
            end_index = prompt.find("]]", key_start_index)
            # replace the variable with the value
            final_prompt = prompt[:start_index] + value + prompt[end_index+2:]
            return final_prompt
        
        prompt = promptstep["prompt"]
        each_var = None
        for var in promptstep["prompt_var_dependancies"]:
            if ".each" in var:
                each_var = var
                continue
            # var is already varized
            # can't simply replace the variable with the value because the variable might have whitespace around it
            # we'll use the varized version of the variable to replace it, handling whitespace and square brackets after the find
            # first find the first variable in the prompt
            prompt = insert_variable(var, variables[var], prompt)
            
        if each_var:
            # handle .each_integer variables. Find the integer and split the list into chunks of size integer
            possible_int = each_var.split(".each")[1]
            if possible_int.isdigit():
                # find the integer
                chunk_size = int(possible_int)
                each_var = each_var.split(".each")[0] + ".each"  # remove the integer from the variable name
                if variables[each_var] == []:
                    raise ValueError(f"Variable {each_var} is empty (likely because none of the llm outputs were parsed as a python list in the previous step). Can't run a .each promptstep accross an empty list")
            else:
                chunk_size = 1

            # run through the list of each_var elements and put the prompt around each element
            prompt_list = []
            chunk = []
            #print(variables)
            #import code; code.interact(local={**globals(), **locals()})
            for each_element in variables[each_var]:
                chunk.append(each_element)
                if len(chunk) == chunk_size:
                    # take every chunk, append them together, and add them to the prompt_list
                    string_chunk = separator.join(chunk)
                    new_filled_prompt = insert_variable(each_var+str(chunk_size), string_chunk, prompt)
                    prompt_list.append(new_filled_prompt)
                    chunk = []
            # print(json.dumps(prompt_list, indent=4))
            # import code; code.interact(local={**globals(), **locals()})
            return prompt_list
        else:
            return [prompt]
    
    def promptstep_var_check(self, variables, promptstep):
        # check if all prompt_var_dependancies are in the variables
        for var in promptstep["prompt_var_dependancies"]:
            if ".each" in var:
                # drop everything after .each in the variable name
                var = var.split(".each")[0] + ".each"
            if var not in variables.keys():
                return False
        return True
    
    def promptchain_var_dependency_check(self, variables, promptchain):
        # mock execution of the promptchain (for loop version)
        # we'll slowly add to the variables as we go through the steps, and check if the step variables are in the dictionary. If not, we'll raise an error (var ___ doesn't exist at this promptstep. Current variables ___). If they are, we'll add the step output to the dictionary. 
        # type check variables and promptchain
        if not isinstance(variables, dict):
            raise TypeError("variables must be a dictionary")
        if not isinstance(promptchain, list):
            raise TypeError("promptchain must be a list")
        for promptstep in promptchain:
            if not isinstance(promptstep, dict):
                raise TypeError("promptchain must be a list of dictionaries")
            # dict must have the following keys: "prompt_var_dependancies", "output_var_name"
            if "prompt_var_dependancies" not in promptstep.keys():
                raise ValueError("promptstep dict must have a 'prompt_var_dependancies' key")
            if "output_var_name" not in promptstep.keys():
                raise ValueError("promptstep dict must have a 'output_var_name' key")
        # for each promptchain step check if all prompt_var_dependancies are in the variables
        for promptstep in promptchain:
            for var in promptstep["prompt_var_dependancies"]:
                var = self.handle_variably_named_vars(var)
                if var not in variables.keys():
                    raise ValueError(f"var {var} doesn't exist at this promptstep. Current variables {variables.keys()}")
            # add the output_var_names to the variables (b/c they are the output of the promptsteps and are now available for the next promptsteps)
            for var in promptstep["output_var_name"]:
                variables[var] = f"output of {var}"



    def find_prompt_variables(self, prompt):
        # find all prompt variables (surrounded by [[ ]]) in the prompt
        # returns a list of the prompt variables
        prompt_variables = []
        # find the first [[
        start_index = prompt.find("[[") 
        max_itterations = 10000
        while start_index != -1:
            max_itterations -= 1
            if max_itterations == 0:
                raise ValueError("Max itterations reached. This is likely due to an infinite loop in the prompt variable search")
            # find the next ]]
            end_index = prompt.find("]]", start_index)
            if end_index == -1:
                Warning("Unmatched [[ in the prompt")
            variable = prompt[start_index+2:end_index].strip()
            if not self.is_varized(variable): 
                # import code; code.interact(local={**globals(), **locals()})
                raise ValueError(f"[[{variable}]] is not varized. Please lowercase all characters and replace spaces with underscores.\nExample: turn '{variable}' into '{self.varize(variable)}'")
            # raise error when there is more than 1 "." character in the variable
            if variable.count(".") > 1 and ".each." not in variable:
                raise ValueError(f"Variable {variable} has more than one '.' character. Variables can only have one '.' character, unless it's an 'each' variable.")
            # add the prompt variable to the list
            prompt_variables.append(variable)
            # find the next [[
            start_index = prompt.find("[[", end_index)
        return prompt_variables

    def is_line_match(self, line, match):
        # return True if line is a match for match expression
        return match.lower() in line.lower()

    def first_line_match_index(self, text, match):
        # returns the text index of the first match
        # split text into lines
        lines = text.split("\n")
        text_mem = ""
        for i, line in enumerate(lines):
            if not self.is_line_match(line, match):
                text_mem = text_mem + "\n" + line
            else:
                # return the length of the text before the match plus the length of the matched line
                return len(text_mem) + len(line)
        return -1
        
    def heading_grab(self, line):  # remove all leading #s from the line
        return line.lstrip("#").strip()
    
    def varize(self, line):  # replace spaces with underscores
        return line.strip().lower().replace(" ", "_")
    
    def is_varized(self, str_):  # check if a string is varized
        if str_.strip().lower().replace(" ", "_") == str_.strip():
            return True
        return False
    
    def parse_variables_from_text(self, variables_text, inline_comment="##", drop_name_and_prompt=False):
        # for each - line, split by ":"
        # on the left, strip whitespace, lowercase the text, and replace spaces with underscores. This is the variable name
        # on the right, gather all the lines until the next - line or the end of the text. This is the variable value
        # add the variable name and value to the variables dictionary
        variables = {}
        lines = variables_text.split("\n")
        # everything before the first newline is the name of this section. Remove starting #s
        section_name = self.heading_grab(lines[0])
        variables["name"] = section_name
        lines = lines[1:]
        # remove remaining lines that start with inline_comment
        lines = [line for line in lines if not line.startswith(inline_comment)]
        # remove the ends of line segments that have inline_comment match
        lines = [line.split(inline_comment)[0] for line in lines]

        text_mem = ""
        last_var_name = None
        found_prompt = False
        for line in lines:
            # text_mem = text_mem + "\n" + line
            if line.startswith("- ") and ":" in line:
                if not found_prompt:
                    found_prompt = True
                    variables["prompt"] = text_mem.strip()
                if last_var_name:
                    # add text_mem as this section's prompt
                    # add to the variables
                    variables[last_var_name] = text_mem.strip()
                # get the new variable name
                var_name_raw = line.split(":")[0]
                var_name = var_name_raw[1:].strip().lower().replace(" ", "_")
                # clear the text_mem
                text_mem = line.split(":")[1]
                last_var_name = var_name
            else:
                text_mem = text_mem + "\n" + line
        # resolve case where there was no variables
        if not found_prompt:
            found_prompt = True
            variables["prompt"] = text_mem.strip()
        # add the last variable
        if last_var_name:
            # add to the variables
            variables[last_var_name] = text_mem.strip()
        if drop_name_and_prompt:
            variables.pop("name", None)
            variables.pop("prompt", None)
        return variables
    
    def get_md(self, variables, prompt_chain):
        # return the md format of the variables and prompt_chain
        md = "## Variables"
        for k, v in variables.items():
            # if v.strip() != "":
            md += f"\n- {k}: {v}"
        if prompt_chain:
            first_prompt_metadata = prompt_chain[0]["metadata"]
            for promptstep in prompt_chain:
                md += f"\n\n{self.separator} {promptstep['name']}\n{promptstep['prompt'].lstrip()}"
                for k, v in promptstep["metadata"].items():
                    # only add the metadata if it's different from the first prompt metadata
                    if first_prompt_metadata.get(k) != v or promptstep['count'] == 1:
                        md += f"\n- {k}: {v}"
        return md
    
    def generate_statefile(self, variables, promptsteps, display_index, starter_variables, var_filled_prompt=None, stats=None):
        # print(json.dumps(promptsteps, indent=4))
        # import code; code.interact(local={**globals(), **locals()})
        # get the first promptstep
        promptstep = promptsteps[display_index]
        # check for key existence, raise error if not found
        for key in ["name", "prompt", "metadata", "count"]:
            if key not in promptstep.keys():
                raise ValueError(f"promptstep dict must have a '{key}' key")
        # return md format of a single promptstep
        md = f"{self.separator} {promptstep['name']}\n{promptstep['prompt'].lstrip()}"
        for k, v in promptstep["metadata"].items():
            md += f"\n- {k}: {v}"
        md += f"\n{self.separator}{self.separator}"
        # add the stats
        if stats:
            md += f" Stats\n{stats}\n"
            md += f"{self.separator}{self.separator}"
        # add the filled prompt
        if var_filled_prompt:
            md += f" Variable Filled Prompt {promptstep['count']}\n{var_filled_prompt}\n"
            md += f"{self.separator}{self.separator}"
        # add the starter variables
        for k, v in starter_variables.items():
            md += f"\n- {k}: {v}"
        md += f"\n{self.separator}{self.separator}"
        # now json dumps the variables and the promptsteps
        # add the variables
        md += "\n"+ json.dumps(variables, indent=4)
        # add another double seperator to seperate the variables from the promptsteps
        md += f"\n{self.separator}{self.separator}\n"
        # add the promptsteps to afford future step editing
        md += json.dumps(promptsteps, indent=4)
        # print(json.dumps(promptsteps, indent=4))
        # import code; code.interact(local={**globals(), **locals()})
        return md
    
    def parse_statefile(self, statefile):
        # get the variables and promptsteps from the statefile
        # return the variables and promptsteps
        # split the statefile by the double seperator
        sections = statefile.split(f"{self.separator}{self.separator}")
        # second to last section is the variables
        variables = json.loads(sections[-2])
        # last section is the remaining promptsteps
        promptsteps = json.loads(sections[-1])
        return variables, promptsteps
        

if __name__ == "__main__": 
    t0 = time.time()
    parser = PromptChainParser()
    result = parser.md_promptchain_parser(md_input_)
    print(json.dumps(result, indent=4))
    print(parser.get_md(result["variables"], result["promptchain"]))
    print("Execution time:", time.time()-t0)

