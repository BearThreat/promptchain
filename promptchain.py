"""
async PromptChain python script to automate the completion of a chain of promptsteps
given a list of promptsteps(potentially dependent on the outputs of previous promptsteps), this script will complete the entire list of promptsteps (in parallel if possible)
return the promptstep outputs in order as a generator(does this allow for querying the generator for the existance of the next value?)
note that promptsteps may be executed in parallel if they are independent of each other
therefore we will use a kind of event architecture to signal when a promptstep is complete and load the next independent promptsteps
promptsteps are dependent when it's a string with missing values that are filled in by the outputs of previous promptsteps or variables
promptsteps are independent when the string has no missing values or the missing values are filled in by previous promptstep outputs
a promptstep is a string (potentially with missing values to be filled later) 
PromptChain will be the class that takes in a list of promptsteps and dictionary variables and completes the promptsteps. It will return the promptstep outputs in list order 
PromptChain will need to manage the variables that are passed between promptsteps using a dictionary
automatically name the output variables of the promptsteps as the promptstep index + 1 (add it to the dictionary)
outputs for each promptstep will be returned in order as a generator that waits to return until the next output has completed (even if that is a long time)

I think this is a python step_futures problem:
given a list of tasks, each depending on (a random number between 0 and n) earlier tasks, execute all these tasks in the most efficient manner possible. I imagine the solution will involve first checking for all tasks with no dependancies, then creating a future for each of these tasks. Whenever a future completes, repeat the task dependency checks ect...
only wait until the FIRST future is complete. This optimization will require us to wait when we have only have tasks with dependancies (we'll be waiting for earlier tasks to complete)
"""

import random, time, asyncio, json, copy
from openrouter_engine import OpenrouterEngine
from promptchain_parser import PromptChainParser


class PromptChain(PromptChainParser, OpenrouterEngine):
    def __init__(self, pr=False):
        PromptChainParser.__init__(self)
        OpenrouterEngine.__init__(self, checkup=False)
        self.pr = pr
        # holds queue of latest unpopped steps for each promptchain(execute_steps) function call id. The queue is ALWAYS ordered by promptstep count
        self.step_progress_queues = {}
    
    def start(self):
        asyncio.create_task(self.hourly_model_checkup())

    def find_runnable_promptsteps(self, variables, promptsteps):
        runnable_steps = []
        non_runnable_steps = []
        for promptstep in promptsteps:
            ready = self.promptstep_var_check(variables, promptstep)
            if self.pr: print(f'Promptstep {promptstep.get("count")} is ready: {ready}')
            if ready:
                runnable_steps.append(promptstep)
            else:
                non_runnable_steps.append(promptstep)
        return runnable_steps, non_runnable_steps

    async def execute_steps(self, variables_, promptsteps, job_id=None):
        completed_step_results = []
        pending_steps = copy.deepcopy(promptsteps)
        variables = copy.deepcopy(variables_)
        step_futures = []
        # define step progress queue that is accessible outside of this function and updates while the function is running. It must also be unique to each instance of this function
        # job_id is a unique float to identify the instance of this function, it's usually a timestamp
        if job_id:
            if isinstance(job_id, float):
                self.step_progress_queues[job_id] = {}
                self.step_progress_queues[job_id]["print_ready_queue"] = []
                self.step_progress_queues[job_id]['error_queue'] = [[] for _ in range(len(promptsteps))]
                self.step_progress_queues[job_id]["promptsteps"] = copy.deepcopy(promptsteps)
                next_progress_queue_index = 0
            else:
                raise Exception("job_id must be a float")
            

        while len(pending_steps) > 0 or len(step_futures) > 0:
            if self.pr:
                # print(json.dumps(variables, indent=4))
                print(json.dumps(list(variables.keys()), indent=4))
                print(f'completed steps: {len(completed_step_results)}')
                print(f'Pending steps: {len(pending_steps)}')
                print(f'Step futures: {len(step_futures)}')
            # Find all promptsteps that are 100% filled by the current variables
            new_executable_steps, steps_awaiting_variables = self.find_runnable_promptsteps(variables, pending_steps)
            # serial_debugging = True
            # if serial_debugging:
            #     if len(new_executable_steps) >= 1 and step_futures == []:
            #         new_executable_steps_ = [new_executable_steps[0]]
            #         if len(new_executable_steps) > 1:
            #             steps_awaiting_variables = new_executable_steps[1:] + steps_awaiting_variables
            #         new_executable_steps = copy.deepcopy(new_executable_steps_)
            if self.pr: print(f'Executable steps: {len(new_executable_steps)}')
            #import code; code.interact(local={**locals(), **globals()})
            # remove the executable steps from the pending steps
            pending_steps = copy.deepcopy(steps_awaiting_variables)

            if len(new_executable_steps) > 0:
                # Create tasks for each executable promptstep
                coroutine_tasks = [self.execute_step(variables, promptstep) for promptstep in new_executable_steps]
                # # serial debugging
                # if serial_debugging:
                #     # if
                # coroutine_tasks = [self.execute_step(variables, new_executable_steps.pop(0))]
                #import code; code.interact(local={**locals(), **globals()})
                # Run the tasks concurrently (in parallel), don't wait for them to complete

                new_step_futures = []
                # set the name of each coroutine task to the promptstep count
                for i, co_task in enumerate(coroutine_tasks):
                    new_step_future = asyncio.create_task(co_task)
                    new_step_future.set_name(new_executable_steps[i].get("count"))
                    new_step_futures.append(new_step_future)
                if self.pr: print(f'New step futures: {len(new_step_futures)}')
                step_futures.extend(new_step_futures)
            else:
                # Wait for at least one step future to complete
                future_check = [future.done() for future in step_futures]
                if self.pr: print(future_check)
                while not any(future_check):
                    if self.pr: print(future_check)
                    for future in step_futures:
                        if future.done():
                            exception = future.exception()
                            if exception is not None:
                                raise Exception(f"Future exception: {exception}")
                    await asyncio.sleep(0.1)
                    future_check = [future.done() for future in step_futures]
                # find the completed futures
                completed_futures = [future for future in step_futures if future.done()]
                for completed_future in completed_futures:
                    try:
                        completed_results = completed_future.result()
                        # remove the completed future from the step_futures list
                        step_futures = [future for future in step_futures if future.get_name() != completed_future.get_name()]
                        # import code; code.interact(local={**locals(), **globals()})

                        # put the output of the completed promptstep into completed_step_results
                        completed_step_results.append(completed_results)
                        if self.pr: print(f'Completed step {completed_results["promptstep"]["count"]}')
                        # update the variables dictionary with the output of the completed promptstep
                        variables = await self.update_variables(variables, completed_results["promptstep"], completed_results["output"])
                        # print(json.dumps(variables, indent=4))
                        #import code; code.interact(local={**locals(), **globals()})
                        # sort the completed_step_results by the promptstep count
                        completed_step_results.sort(key=lambda x: x["promptstep"]["count"])
                        # add the completed step to the step progress queue
                        # look at all the completed step count numbers and if next one is in completed_step_results, add it to the queue and increment the next_progress_queue_index 
                        max_itterations = 10000
                        if self.pr: print(max_itterations)
                        while job_id and next_progress_queue_index + 1 in [completed_step["promptstep"]["count"] for completed_step in completed_step_results]:
                            if max_itterations == 0:
                                raise Exception(f"Max itterations reached. next_progress_queue_index: {next_progress_queue_index}, completed_step_results: {completed_step_results}")
                            max_itterations -= 1
                            if self.pr: print(max_itterations)
                            # find the index of the next promptstep in the completed_step_results and remove it from the list
                            for i, completed_step in enumerate(completed_step_results):
                                if completed_step["promptstep"]["count"] == next_progress_queue_index + 1:
                                    # append the index of the next promptstep in the completed_step_results to the step progress queue
                                    self.step_progress_queues[job_id]["print_ready_queue"].append(completed_step_results[i])
                                    next_progress_queue_index += 1
                                    # break out of the for loop
                                    break
                    except Exception as e:
                        # remove the completed future from the step_futures list
                        step_futures = [future for future in step_futures if future.get_name() != completed_future.get_name()]
                        pending_steps = []
                        self.step_progress_queues[job_id]['error_queue'][int(completed_future.get_name())-1].append(e)
        return completed_step_results


    async def update_variables(self, variables, promptstep, output):
        # update the variables dictionary with the output of the completed promptstep
        # look in promptstep "ouput_var_name" key for list of new variable names to add to the variables dictionary, the values are the output of the promptstep
        new_variables = copy.deepcopy(variables)

        for var_name in promptstep["output_var_name"]:
            print(var_name)
            # new_variables[var_name] = output["completions"][0]
            if var_name.endswith(".all"):
                # combine all completions into a single string separated by 2 newlines
                new_variables[var_name] = "\n\n".join(output["completions"])
            elif "." not in var_name or var_name.endswith(".1"):
                new_variables[var_name] = output["completions"][0]
            elif "." in var_name and var_name.split(".")[-1].isdigit():
                # the variable name ends with .2, .3, etc. then add the completions to the list
                # get the number at the end of the variable name
                var_num = int(var_name.split(".")[-1])
                # var_num - 1 is the completion index for the output
                new_variables[var_name] = output["completions"][var_num - 1]
            elif ".each" in var_name:
                # completions = list_completions
                new_variables[var_name] = output.get("list_completions", output["completions"])
                #import code; code.interact(local={**locals(), **globals()})
            else:
                # not really sure if this is necessary
                raise Exception(f"Invalid variable name: {var_name}\n\nvariables need to end with .1, .2, .3, etc. to reference the desired completion index")
        if self.pr: 
            print("finished updating variables. All variables:")
            for key, value in new_variables.items():
                print(f'{key}')
        return new_variables

    async def execute_step(self, variables, promptstep):
        if self.pr: print(json.dumps(promptstep, indent=4))
        #import code; code.interact(local={**locals(), **globals()})
        if self.pr: print(f'Executing task {promptstep.get("count")}')
        filled_prompts = self.fill_promptstep_with_variables(variables, promptstep)
        promptstep["filled_prompt"] = copy.deepcopy(filled_prompts)
        if self.pr: print(filled_prompts)
        completions = promptstep.get("metadata", {}).get("completions", 1)
        # remove completions from metadata
        promptstep["metadata"].pop("completions", None)
        # run the promptstep with acomplete
        # run an acomplete for each filled_prompt element in an async gather
        # out = await self.acomplete(promptstep.get("filled_prompt"), completions=completions, **promptstep.get("metadata"))
        each_completions = [self.acomplete(filled_prompt, completions=completions, **promptstep.get("metadata")) for filled_prompt in filled_prompts]
        out = await asyncio.gather(*each_completions)
        
        if self.pr: print(out)

        def merge_outputs(outputs):
            merged_output = outputs[0]
            for output in outputs[1:]:
                for key, value in output.items():
                    if key == 'completions':
                        merged_output[key].extend(value)
                    elif key == 'metadata':
                        merged_output[key].extend(value)
                    elif key == 'runtime':
                        if value > merged_output[key]:
                            merged_output[key] = value
                    else:
                        pass
            # sum the metadata tokens_prompt, avg_tokens_completion, tokens_total, cost_dollars, and avg_cost
            merged_output["tokens_prompt"] = sum([output["tokens_prompt"] for output in merged_output["metadata"] if output["tokens_prompt"] is not None]) / len(merged_output["metadata"])
            merged_output["avg_tokens_completion"] = sum([output["tokens_completion"] for output in merged_output["metadata"] if output["tokens_completion"] is not None]) / len(merged_output["metadata"])
            # (prompt tokens + avg tokens per completion) * completions
            merged_output["tokens_total"] = (merged_output["tokens_prompt"] + merged_output["avg_tokens_completion"]) * len(merged_output["metadata"])
            # sum the cost of each completion
            merged_output["cost_dollars"] = sum([output["usage"] for output in merged_output["metadata"] if output["usage"] is not None])
            # average cost per completion
            merged_output["avg_cost"] = merged_output["cost_dollars"] / len(merged_output["metadata"])
            merged_output["cost_dollars"] = "{:.7f}".format(round(merged_output["cost_dollars"], 7))
            merged_output["avg_cost"] = "{:.7f}".format(round(merged_output["avg_cost"], 7))
            return merged_output
        try:
            print(promptstep)
            print(list(variables.keys()))
            # get the text between [ and .each in the promptstep['prompt']
            dot_each = promptstep["prompt"].find(".each")
            if dot_each != -1:
                var_name = promptstep["prompt"][promptstep["prompt"].rfind("[", 0, dot_each) + 1:dot_each]
                print(variables[var_name]+".each")
            out = merge_outputs(out)
        except Exception as e:
            # variables['copywriter_character_persona.each']
            #import code; code.interact(local={**locals(), **globals()})
            raise Exception(e)
        # print("length of print_ready_queue")
        # print(len(self.step_progress_queues[list(self.step_progress_queues.keys())[0]]["print_ready_queue"]))
        # out = merge_outputs(out)

        #import code; code.interact(local={**locals(), **globals()})
        # for each line in each completion, if it starts with "- " and includes a colon, remove the "- ", if it contains self.separator match then remove each separator match
        out["completions"] = [self.remove_prefixes_and_separators(completion) for completion in out["completions"]]
        # # parse the output of each completion for this promptstep
        # for i, completion in enumerate(out["completions"]):
        #     out["completions"][i] = self.parse_completion(completion)
        prompt_parsing_example = f"""
Tell the model to Return a single Python list of strings in JSON format like so
```json
[
    "Example 1",
    "Example 2",
    "Example 3"
]
```"""
        # parse each completion as json
        list_completions = None
        if "list" in promptstep.get("metadata", {}) and bool(promptstep.get("metadata", {}).get("list", False)) == True:
            list_completions = []
            completion_errors = []
            for idx, completion in enumerate(out["completions"]):
                if self.pr: print(completion)
                if ("```json" in completion or "```JSON" in completion) and completion.count("```") == 2:
                    if self.pr: print(f"Completion {idx} is json")
                    json_location = max(completion.find("```json"), completion.find("```JSON"))
                    json_location_right = json_location + len("```json")
                    second_json_location = completion[json_location_right:].find("```") + json_location_right
                    completion_ = completion[json_location_right: second_json_location]
                    try:
                        completion_ = json.loads(completion_)
                    except Exception as e:
                        err_dict = {"error": str(e)+f"\n{prompt_parsing_example}", "completion": completion}
                        err_json = json.dumps(err_dict, indent=4)
                        err_json = err_json.replace("\\n", "\n").replace("\\\"", "\"").replace("\\'", "'")
                        completion_errors.append(err_json)
                        continue
                    if isinstance(completion_, list) and isinstance(completion_[0], str):
                        # the completion is a list of strings and we can continue
                        if self.pr: print(f"Completion {idx} parsed as json")
                        list_completions.extend(completion_)
                    else:
                        # completion_errors.append(json.dumps({"error": "Completion is not a list of strings", "completion": completion}, indent=4))
                        err_dict = {"error": f"Completion is not parsable as a list of strings. {prompt_parsing_example}", "completion": completion}
                        err_json = json.dumps(err_dict, indent=4)
                        err_json = err_json.replace("\\n", "\n").replace("\\\"", "\"").replace("\\'", "'")
                        completion_errors.append(err_json)
                else:
                    #completion_errors.append(json.dumps({"error": "Completion is not json", "completion": completion}, indent=4))
                    err_dict = {"error": f"Completion is not json parsable. {prompt_parsing_example}", "completion": completion}
                    err_json = json.dumps(err_dict, indent=4)
                    err_json = err_json.replace("\\n", "\n").replace("\\\"", "\"").replace("\\'", "'")
                    completion_errors.append(err_json)
            out["list_completions"] = list_completions
            out["completion_errors"] = completion_errors

        #import code; code.interact(local={**locals(), **globals()})
        return {"promptstep": promptstep, "variables": variables, "output": out}
    
    def remove_prefixes_and_separators(self, completion):
        # exists only to allow for future recursive calls
        # remove "- " prefix to avoid parser confusion
        if completion.startswith("- ") and ":" in completion:
            completion = "* " + completion[2:]
        # remove separator matches
        completion = completion.replace(self.separator, "")
        return completion

    async def run_chain(self, md_promptchain, job_id=None):
        parsed_chain = self.md_promptchain_parser(md_promptchain, models=self.models)
        self.chain_variables = parsed_chain.get("variables")
        self.promptchain_steps = parsed_chain.get("promptchain")
        if self.pr: print(json.dumps(self.chain_variables, indent=4))
        if self.pr: print(json.dumps(self.promptchain_steps, indent=4))

        out = await self.execute_steps(self.chain_variables, self.promptchain_steps, job_id=job_id)
        return out


# Example usage
if __name__ == "__main__":
    md_input = """
## Variables
- context:
an entertaining political email Newsletter

### Prompt 1
Pitch [[ context ]] piece by first ideating a theme and then crafting the ideal audience avatar attributes. Be Very Concise

## Metadata
- model: openai/gpt-3.5-turbo
- temperature: 0
- completions: 1
- scoring_prompt: 

###
[[1]]


Draft [[context]] piece. Address the reader as "[reader]"

### get subject lines
Audience avatar:
[[1]]

[[2]]

Ideate a list of concise subject lines that would appeal to the above audience avatar

## Metadata
- model: openai/gpt-3.5-turbo  ## bestest model for talking about cats
- temperature: 1
- completions: 1
- scoring_prompt: 

### Copywriter character persona
Ideate the ideal copywriter character persona. Someone hardworking, creative, and worldly.

- completions: 3

### select the best writer
[[copywriter_character_persona.all]]

Choose the best writer from the above list of writers


"""

    md_input ="""## Variables
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
Ideate an ideal copywriter character persona. Someone hardworking, intensely creative, and worldly.
- completions: 5
- temperature: 1

### select the best writer
[[copywriter_character_persona.all]]

Select the best 2 writers from the above list of copywriter character personas. Return a single Python list of strings in JSON format like so
```json
[
    'Character Choice 1: Character Background 1',
    'Character Choice 2: Character Background 2',
]
```
- model: anthropic/claude-3-haiku
- list: True

"""
    md_input ="""
### Copywriter character persona
Ideate 3 ideal copywriter character personas. Someone hardworking, creative, and worldly. Return a single Python list of strings in JSON format like so
```json
[
    "Character 1 Name: Character Background 1",
    "Character 2 Name: Character Background 2",
    "Character 3 Name: Character Background 3"
]
```

- model: openai/gpt-3.5-turbo
- completions: 5
- list: True
### elaborate on the copywriter character persona
[[copywriter_character_persona.each3]]

Continue the copywriter character personas by elaborating on the character's background, personality, and work ethic. Don't discuss ANYTHING else, just expand the character personas.
### select the best writer
[[elaborate_on_the_copywriter_character_persona.all]]

Select the best 2 writers from the above list of copywriter character personas.
"""
    async def main():
        prompt_chain = PromptChain(pr=True)
        prompt_chain.start()
        # wait until self.models dictionary is populated. Can't await start_task because it's an inf loop
        async def wait_for_models(): 
            max_itterations = 100
            while prompt_chain.models == {}:
                max_itterations -= 1
                print(max_itterations)
                if max_itterations <= 0:
                    raise Exception("Max itterations reached. Models not loaded")
                await asyncio.sleep(0.1)
            print("Models first loaded")
        await wait_for_models()
        
        # print(json.dumps(prompt_chain.models, indent=4))
        # import code; code.interact(local={**locals(), **globals()})

        run_chain_task = asyncio.create_task(prompt_chain.run_chain(md_input))
        return await run_chain_task

    t0 = time.time()
    out = asyncio.run(main())
    print(json.dumps(out, indent=4))
    print(f'Time taken: {time.time() - t0}')
    # print(json.dumps(out[1]["promptstep"]["filled_prompt"], indent=4))
    # import code; code.interact(local={**locals(), **globals()})



