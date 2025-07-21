import os, json, asyncio, time, aiohttp, re, random, copy
from dotenv import load_dotenv
from openai import OpenAI
from openai import AsyncOpenAI
import requests, tiktoken


def validate_parameters(include_default_values=False, keep_extra_keys=False, **kwargs):
    parameters = {}
    # first check if the model is valid
    # if "model" in list(kwargs.keys()) and kwargs.get("model") in self.models.keys():
    #     # add the model to the parameters
    #     parameters['model'] = kwargs['model']
    # else:
    #     raise ValueError(f"Invalid model: {kwargs.get('model')}. Please use one of the following models: {list(self.models.keys())}")
    if kwargs.get('model', None) is None:
        raise ValueError("model is a required parameter.")
    parameters['model'] = kwargs['model']
    # Default values
    default_values = {
        "temperature": 1.0, "top_p": 1.0, "top_k": 0, "frequency_penalty": 0.0,
        "presence_penalty": 0.0, "repetition_penalty": 1.0, "min_p": 0.0,
        "top_a": 0.0, "seed": None, "max_tokens": None, "logit_bias": {}, 
        "response_format": {}, "stop": [], "stream": False,
    }
    # Validation and assignment with type validation
    for key, default_value in default_values.items():
        value = kwargs.get(key, default_value)
        if key in ["temperature", "top_p", "frequency_penalty", "presence_penalty", "repetition_penalty", "min_p", "top_a"]:
            if not isinstance(value, (int, float)):
                raise TypeError(f"{key} must be a float.")
            if key in ["temperature", "top_p", "frequency_penalty", "presence_penalty", "repetition_penalty", "min_p", "top_a"]:
                if value < 0.0 or value > 2.0:
                    raise ValueError(f"{key} must be between 0.0 and 2.0.")
        elif key == "top_k":
            if not isinstance(value, int):
                raise TypeError(f"{key} must be an integer.")
            if value < 0:
                raise ValueError(f"{key} must be 0 or above.")
        elif key == "seed":
            if value is not None and not isinstance(value, int):
                raise TypeError(f"{key} must be an integer or None.")
        elif key == "max_tokens":
            if value is not None and not isinstance(value, int):
                raise TypeError(f"{key} must be an integer or None.")
        elif key == "logit_bias" or key == "response_format":
            if not isinstance(value, dict):
                raise TypeError(f"{key} must be a dictionary.")
        elif key == "stop":
            if not isinstance(value, list):
                raise TypeError(f"{key} must be a list.")
        elif key == "stream":
            if not isinstance(value, bool):
                raise TypeError(f"{key} must be a boolean.")
        # Only add the parameter to the final dictionary if it's not the default value
        if value != default_value or include_default_values or key in kwargs.keys():
            parameters[key] = value
    if keep_extra_keys:
        # Add any extra keys that are not in the default_values
        for key, value in kwargs.items():
            if key not in default_values:
                parameters[key] = value
    return parameters

class APIRequestError(Exception):
    def __init__(self, status_code, message):
        self.status_code = status_code
        self.message = message
        super().__init__(f"API request failed with status code {status_code}: {message}")

class RetryExceededError(Exception):
    def __init__(self, max_retries):
        self.max_retries = max_retries
        super().__init__(f"Max retries ({max_retries}) exceeded for API request")

class Stream:
    def __init__(self, response, headers, base_url, t0):
        self.response = response; self.headers = headers
        self.base_url = base_url; self.start_time = t0
        self.chunks = asyncio.Queue()
        self.generation_metadata = None

    async def start(self):
        async for chunk in self.response:
            await self.chunks.put(chunk)
        # Fetch generation metadata after the stream completes
        self.generation_metadata = self.send_generation_metadata(self.response.json()['id'])
        full_reply_content = await self.get_full_reply_content()
        return {"completion": full_reply_content, "metadata": self.generation_metadata, "time": f"{time.time() - self.start_time:.6f}"}
    
    async def get_full_reply_content(self, empty_queue=False):
        full_reply_content = ""
        index = 0
        while not self.chunks.empty():
            if empty_queue:
                # Empty the queue element as we go
                chunk = await self.chunks.get()
            else:
                # Peek at the queue element without removing it
                chunk = self.chunks.queue[index]
            full_reply_content += chunk.choices[0].delta.content
            index += 1
        return full_reply_content

    async def get_latest_chunk(self):
        return await self.chunks.get()

    async def send_generation_metadata(self, generation_id, max_retries=3, base_delay=1):
        retry_count = 0
        while retry_count < max_retries:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url=self.base_url + f"/generation?id={generation_id}",
                        headers=self.headers
                    ) as response:
                        if response.status == 200:
                            response_cost = await response.json()
                            return response_cost
                        else:
                            raise APIRequestError(response.status, "Unexpected status code")
            except APIRequestError as e:
                retry_count += 1
                if retry_count < max_retries:
                    delay = base_delay * (2 ** (retry_count - 1))
                    jitter = random.uniform(0, delay * 0.1)
                    delay += jitter
                    await asyncio.sleep(delay)
                else:
                    raise RetryExceededError(max_retries) from e
            except Exception as e:
                raise APIRequestError(500, str(e)) from e

        raise RetryExceededError(max_retries)
        

class OpenrouterEngine:
    def __init__(self, model="openai/gpt-3.5-turbo-0125", checkup=False, pr=False, **kwargs):
        load_dotenv(); self.pr = pr; self.send_generation_metadata_total_time = 0
        self.send_generation_metadata_count = 0; self.send_generation_metadata_avg_time = 0
        self.models = {}; self.auth_key_info = {}
        self.client = AsyncOpenAI()
        self.client.base_url = "https://openrouter.ai/api/v1"
        self.client.api_key = os.environ['OPENROUTER_API_KEY']
        self.headers = {
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        }
        if checkup:
            print(asyncio.get_event_loop().is_running())
            # if not already in an event loop, create a new one and run the checkup
            if not asyncio.get_event_loop().is_running():
                print("Running checkup in new event loop")
                asyncio.run(self.openrouter_checkup())
            # else:
                # # if in an event loop, run the checkup in the current event loop
                # print("Running checkup in current event loop")
                # asyncio.get_event_loop().run_until_complete(self.hourly_model_checkup())
        # save in case of immediate run
        self.model = model
        # insert this self.model into kwargs as a key-value pair
        kwargs['model'] = self.model
        self.kwargs = validate_parameters(**kwargs)

    def slack_block_model_list(self):
        slack_block_model_list = []
        for model in self.models.values():
            # use k for thousands
            rounded_context_len = f"{int(model['context_length'] / 1000)}k"
            # model_name = self.safe_text(model['name'])
            model_name = model['name']
            slack_block_model_list.append({
                "text": {
                    "type": "plain_text",
                    "text": f"{model_name} - {rounded_context_len}",
                    "emoji": True
                },
                "value": model['id']
            })
        # limit the list to 100 models
        if len(slack_block_model_list) > 100:
            slack_block_model_list = slack_block_model_list[:100]
        return slack_block_model_list

    def safe_text(self, text):
        # encode the text to ascii
        return text.encode('ascii', 'ignore').decode('ascii')

    def word_count(self, text):
        return len(re.findall(r'\b\w+\b', text))
    
    def sort_models(self):
        # sort the models by id. openai first, then anthropic, then gemini, then mistral, then everything else
        # we must maintain the order of the models in the dictionary
        models_list = copy.deepcopy(list(self.models.values()))
        sorted_models_list = []
        
        def seperate_models(string_match, models_list_, sorted_models_list):
            models_list = copy.deepcopy(models_list_)
            for model in models_list_:
                if str(string_match).lower() in str(model['id']).lower() or \
                    str(string_match).lower() in str(model['name']).lower():
                    sorted_models_list.append(model)
                    # remove the model from the list to make the list smaller
                    models_list.remove(model)
            return sorted_models_list, models_list
        
        # anthropic models
        sorted_models_list, models_list = seperate_models("anthropic", models_list, sorted_models_list)
        # openai models
        sorted_models_list, models_list = seperate_models("openai", models_list, sorted_models_list)
        # mythomax models
        sorted_models_list, models_list = seperate_models("mythomax", models_list, sorted_models_list)
        sorted_models_list, models_list = seperate_models("llama", models_list, sorted_models_list)
        # mistral models
        sorted_models_list, models_list = seperate_models("mistral", models_list, sorted_models_list)
        # gemini models
        sorted_models_list, models_list = seperate_models("gemini", models_list, sorted_models_list)
        # everything else
        for model in models_list:
            sorted_models_list.append(model)

        # for model in self.models.values():
        #     if "openai" in str(model['id']):
        #         sorted_models_list.append(model)
        #         #if self.pr: print(json.dumps(model, indent=2))
        # for model in self.models.values():
        #     if "anthropic" in str(model['id']):
        #         sorted_models_list.append(model)
        #         #if self.pr: print(json.dumps(model, indent=2))
        # for model in self.models.values():
        #     if "gemini" in str(model['id']):
        #         sorted_models_list.append(model)
        #         #if self.pr: print(json.dumps(model, indent=2))
        # for model in self.models.values():
        #     if "mistral" in str(model['id']):
        #         sorted_models_list.append(model)
        #         #if self.pr: print(json.dumps(model, indent=2))

        # for model in self.models.values():
        #     if "gryphe/mythomax-l2-13b" in str(model['id']):
        #         sorted_models_list.append(model)
        #         #if self.pr: print(json.dumps(model, indent=2))

        # # lol, this is a pointless exercise b/c openrouter is a service for commercial use, meaning all models are commercial by default
        # # # drop models with the following in their id b/c of non-commercial use
        # # drop_models = ["Vicuna-33B", "MPT-30B-chat", "SOLAR-10.7B-Instruct-v1.0", "Starling-LM-7B-alpha", "Guanaco-33B", "Koala-13B", "GPT4All-13B-Snoozy", "MPT-7B-Chat", "Alpaca-13B", "ChatGLM-6B", "StableLM-Tuned-Alpha-7B", "LLaMA-13B"]
        # # # drop when perfect name or id match is found
        # # for model in self.models.values():
        # #     for drop_model in drop_models:
        # #         if drop_model in str(model['id']) or drop_model in str(model['name']):
        # #             if self.pr: print(f"Drop model: {model['id']}")
        # #             sorted_models_list.remove(model)
        # #         # print models with 80% name or id match 
        # #         elif fuzz.ratio(drop_model, model['id']) > 80:
        # #             if self.pr: print(f"Possible drop model: {model['id']}")
        # #         elif fuzz.ratio(drop_model, model['name']) > 80:
        # #             if self.pr: print(f"Possible drop model: {model['name']}")

                
        # # everything else
        # for model in self.models.values():
        #     if "openai" not in str(model['id']) and "anthropic" not in str(model['id']) and "gemini" not in str(model['id']) and "mistral" not in str(model['id']):
        #         sorted_models_list.append(model)
                #if self.pr: print(json.dumps(model, indent=2))
        # convert the list to an ordered dictionary
        sorted_models = {}
        for model in sorted_models_list:
            sorted_models[model['id']] = model
            if self.pr: print(json.dumps(model, indent=2))
        self.models = sorted_models
        # # save to pickle file
        # import pickle
        # with open('models.pkl', 'wb') as f:
        #     pickle.dump(self.models, f, pickle.HIGHEST_PROTOCOL)
        # exit()


    async def get_model_metadata(self):
        backoff = 1  # initial backoff delay in seconds
        max_backoff = 60  # max backoff delay in seconds

        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url=str(self.client.base_url) + "models",
                        headers=self.headers
                    ) as response:
                        response.raise_for_status()  # raise exception if the request failed
                        response_model = await response.json()
                        if self.pr: print(json.dumps(response_model['data'][0], indent=2))
                        self.models = {}
                        for model in response_model['data']:
                            self.models[model['id']] = model
                        # sort the models
                        self.sort_models()
                        break  # break the loop if the request was successful
            except Exception as e:
                if backoff > max_backoff:
                    raise e  # re-raise the last exception if the max backoff is exceeded
                jitter = random.uniform(0, 0.2)  # add some randomness to the backoff delay
                sleep_time = backoff + (backoff * jitter)
                await asyncio.sleep(sleep_time)  # wait before retrying
                backoff *= 2  # double the backoff delay

    async def get_auth_key_info(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url=str(self.client.base_url) + "auth/key",
                headers=self.headers
            ) as response:
                response_key = await response.json()
                if self.pr: print(json.dumps(response_key, indent=2))
                self.auth_key_info = response_key

    async def get_rankings(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url="https://openrouter.ai/" + "rankings",
                headers=self.headers
            ) as response:
                response_rankings = response # await response.json()
                content = await response_rankings.content.read()
                #print(json.dumps(response_rankings, indent=2))
                import code; code.interact(local=locals())
                return response_rankings

    async def openrouter_checkup(self):
        t0 = time.time()
        checkup_task = asyncio.gather(
            self.get_model_metadata(),
            self.get_auth_key_info()
        )
        print("Running openrouter checkup")
        finish = await checkup_task
        print("Openrouter checkup finished")
        # sort the models by id
        self.sort_models()
        print("Models sorted")
        if self.pr: print(f"Openrouter checkup took {time.time() - t0:.2f} seconds")
        # print(f"Openrouter checkup took {time.time() - t0:.2f} seconds")


    async def hourly_model_checkup(self, check_every=3600):
        while True:
            print("Running hourly model checkup")
            await self.openrouter_checkup()
            await asyncio.sleep(check_every)
    
    async def suggest_parameters(self, model):
        # suggest popular parameters for this model /parameters/{model}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url=str(self.client.base_url) + f"/parameters/{model}",
                headers=self.headers
            ) as response:
                response_parameters = await response.json()
                if self.pr: print(json.dumps(response_parameters, indent=2))
                return response_parameters
            
    def request_error_code_raise(self, response):
        print(response)
        import code; code.interact(local=locals())
        if response.status_code != 200:
            raise Exception(f"Error {response.status_code}: {response.json()['error']}")
        return response
    
    def is_parsable_json(string):
        try:
            json.loads(string)
            return True
        except Exception as e:
            return False

    async def _acomplete(self, prompt, metadata=True, max_retries=5, **kwargs):
        # pass the model to the kwargs if it's not already there
        if 'model' not in kwargs:
            kwargs['model'] = self.model
        t0=time.time();validated_kwargs = validate_parameters(**kwargs); cost = 0
        if isinstance(prompt, str):
            # if the string is parsable json in the format of a list of dictionaries with role and content keys (values of both are strings) then parse it as such
            try:
                # if self.is_parsable_json(prompt):
                prompt1 = prompt.encode('unicode-escape').decode()
                prompt = json.loads(prompt1)
                # import code; code.interact(local={**locals(), **globals()})
                if self.pr: print(f"Prompt: {prompt}")
                # check if the prompt is a list of dictionaries with role and content keys
                if isinstance(prompt, list) and isinstance(prompt[0], dict) and all(isinstance(item, dict) and 'role' in item and 'content' in item and isinstance(item['role'], str) and isinstance(item['content'], str) for item in prompt):
                    messages = prompt
                else:
                    raise TypeError("prompt must be a string or a list of dictionaries with role and content keys. E.g., [{'role': 'user', 'content': 'Hello, world!'}]")
            except Exception as e:
                print(f"prompt: {prompt}\n\n{e}")
                # import code; code.interact(local={**locals(), **globals()})
                messages = [{'role': 'user', 'content': prompt}]
            # messages = None 
            # # add prompt and transforms to the kwargs
            # # transforms = [] # Compress prompts > context size. This is the default for all models.
            # validated_kwargs = {"prompt": prompt, **validated_kwargs}
        elif isinstance(prompt, list) and isinstance(prompt[0], dict):
            messages = prompt
        else:
            raise TypeError("prompt must be a string or a list of dictionaries. E.g., [{'role': 'user', 'content': 'Hello, world!'}]"+f"\nprompt: >>{prompt}<<")

        if validated_kwargs.get('stream', None):  # Streaming mode
            try:
                response = self.client.chat.completions.create(
                    messages=messages,
                    **validated_kwargs,
                )
                # response = self.request_error_code_raise(response)
            except TypeError or ValueError as e:
                # suggest popular parameters for this model
                parameters = await self.suggest_parameters(validated_kwargs['model'])
                raise Exception(f"{e}\n\nOpenrouter's suggested parameters: {json.dumps(parameters, indent=2)}")
            stream = Stream(response, self.headers, self.client.base_url, t0)
            # outside methods will need to call stream.start() and handle the stream
            return stream
        else:
            retries = 0
            while retries < max_retries:
                try:
                    response = await self.client.chat.completions.create(
                        messages=messages,
                        **validated_kwargs,
                    )
                    if hasattr(response, 'error'):
                        error_message = response.error.get('message', 'Unknown error')
                        error_code = response.error.get('code', 'Unknown code')
                        raise Exception(f"API Error: {error_message} (Code: {error_code})")
                    if self.pr: print(response)
                    if response.choices:
                        completion = response.choices[0].message.content
                    else:
                        raise Exception(f"Openrouter response.choices is null: {response}")
                    if metadata:
                        generation_metadata = await self.send_generation_metadata(response.id)
                        cost = generation_metadata.get('data', {}).get('usage')
                    else:
                        generation_metadata = {}
                    break  # Exit the loop if the request is successful
                except (TypeError, ValueError) as e:
                    parameters = await self.suggest_parameters(validated_kwargs['model'])
                    raise Exception(f"{e}\n\nOpenrouter's suggested parameters for this model: {json.dumps(parameters, indent=2)}")
                except Exception as e:
                    if retries < max_retries - 1 and hasattr(response, 'error') and 500 <= response.error.get('code', 500) < 600:
                        wait_time = 2 ** retries  # Exponential backoff
                        print(f"Request failed with exception: {e}. Retrying in {wait_time} seconds...")
                        await asyncio.sleep(wait_time)
                        retries += 1
                    elif retries == max_retries - 1:
                        print("Max retries reached. Giving up.")
                        raise Exception(f"Max retries {max_retries} reached with error: {e}\n\n{response}")
                    else:
                        raise Exception(f"Error: {e}\n\n{response}")
            return {'completions': [completion], 'metadata': generation_metadata.get('data'), 'kwargs': validate_parameters(include_default_values=True, **kwargs), 'time': time.time() - t0, 'cost': cost}
    
    async def acomplete(self, prompt, completions=1, **kwargs):
        # pass the model to the kwargs if it's not already there
        if 'model' not in kwargs:
            kwargs['model'] = self.model
        if completions <= 1:
            output = await self._acomplete(prompt, **kwargs)
            output['metadata'] = [output['metadata']]
        else:
            # Multiple completions in parallel non-streaming mode. Sum the costs
            t0 = time.time()
            completions_ = [self._acomplete(prompt, **kwargs) for _ in range(completions)]
            # import code; code.interact(local={**locals(), **globals()})
            results = await asyncio.gather(*completions_)
            total_time = time.time() - t0
            if self.pr: print(f"Total time for {completions} completions: {total_time:.2f} seconds")
            # put all the completions in a list
            completions__ = [result['completions'][0] for result in results]
            # put all the metadata in a list
            metadata = [result['metadata'] for result in results]
            # sum the costs
            cost = sum([result['cost'] if result['cost'] is not None else 0 for result in results])
            # if results[0].get('metadata'):
            # else:
            #     metadata = None; cost = None
            output = {'completions': completions__, 'metadata': metadata, 'time': total_time, 'cost': cost}
        # get more info from the response metadata
        validated_kwargs = validate_parameters(include_default_values=True, **kwargs)
        temp = validated_kwargs.get('temperature')
        completions_list = output.get('completions')
        total_completions = len(completions_list)
        metadata = output.get('metadata')
        print(metadata)
        # import code; code.interact(local={**locals(), **globals()})
        # remove null elements from the metadata list
        # metadata = [metadata_ for metadata_ in metadata if metadata_ is not None]
        total_tokens = sum([metadata.get('tokens_prompt') + metadata.get('tokens_completion') for metadata in metadata])
        total_prompt_tokens = sum([metadata.get('tokens_prompt') for metadata in metadata])
        total_completion_tokens = sum([metadata.get('tokens_completion') for metadata in metadata])
        cost = output.get('cost')
        total_time = output.get('time')
        # print the types of every variable that is divided
        return {'prompt': prompt, 'completions': completions_list, 'model': kwargs['model'], 'metadata': metadata, 'runtime': round(total_time, 2), 'temperature': temp, 'completion(s)': completions, 'tokens_total':total_tokens, 'tokens_prompt':int(total_prompt_tokens/total_completions), 'avg_tokens_completion':int(total_completion_tokens/total_completions), 'cost_dollars': "{:.7f}".format(round(cost, 7)), 'avg_cost': "{:.7f}".format(round(cost/total_completions, 7)),}

    async def send_generation_metadata(self, generation_id, timeout=3, retries=3):
        t0 = time.time()
        for attempt in range(retries):
            await asyncio.sleep(2)
            # import code; code.interact(local={**locals(), **globals()})   
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url=str(self.client.base_url) + f"/generation?id={generation_id}",
                        headers=self.headers
                    ) as response:
                        response_cost = await response.json()
                        if self.pr: print(json.dumps(response_cost, indent=2))
                        self.send_generation_metadata_count += 1
                        self.send_generation_metadata_total_time += time.time() - t0
                        self.send_generation_metadata_avg_time = self.send_generation_metadata_total_time / self.send_generation_metadata_count
                        if self.pr: print(f"send_generation_metadata took {time.time() - t0:.2f} seconds")
                        if self.pr: print(f"send_generation_metadata_avg_time: {self.send_generation_metadata_avg_time:.6f} seconds")
                        return response_cost
                # import code; code.interact(local={**locals(), **globals()})    
            except Exception as e:
                if self.pr: print(f"Attempt {attempt + 1} failed with error: {e}")
                # import code; code.interact(local={**locals(), **globals()})
                if attempt < retries - 1: # If it's not the last attempt
                    await asyncio.sleep(timeout) # Wait for the specified timeout
                else:
                    raise # If it's the last attempt, re-raise the exception

    def tok_len(self, text: str, model_name="gpt-3.5-turbo") -> int:
        return len(tiktoken.encoding_for_model(model_name).encode(text))
    
    # cut off first n tokens
    def cut_first_n(self, text: str, n: int, model_name="gpt-3.5-turbo") -> str:
        enc = tiktoken.encoding_for_model(model_name)
        encoded_text = enc.encode(text)[n:]
        return str(enc.decode(encoded_text))
    
    def keep_last_n(self, text: str, n: int, model_name="gpt-3.5-turbo") -> str:
        enc = tiktoken.encoding_for_model(model_name)
        try:
            encoded_text = enc.encode(text)[-n:]
        except IndexError:
            encoded_text = enc.encode(text)
        return str(enc.decode(encoded_text))

    def context_len(self, model_name) -> int:
        if self.models:
            # return 90% of the context length b/c tiktoken is just a proxy for the token length of non-openai models
            return int(int(self.models[model_name]['context_length']) * 0.9)
        else:
            raise ValueError("Models not loaded. Run get_model_metadata() first.")
    
    # summarize an arbitrarily long piece of text using mapreduce + refine prompts
    async def map_summarize(self, text, model="anthropic/claude-3-haiku", chunk_ratio=0.8, max_batch_size=30, temp=0, max_chunk_size=2000, summary_prompt="Write a concise summary of the following:\n\n{text}\n\nCONCISE SUMMARY:", BEGIN=None, END=None, pr=True):
        # algorithm:
        # split text into chunks of chunk_ratio the max context length. Kinda depends on your desired summary length
        # summarise each chunk
        # combine the summaries via a recursive refine prompt
        # return the final summary
        t0 = time.time()
        running_cost = 0
        # split text into chunks of chunk_ratio the max context length using our token length functions
        max_len = self.context_len(model)
        max_len = min(max_len, max_chunk_size)
        chunk_len = int(max_len * chunk_ratio)
        overlap = int(chunk_len * 0.1)
        if pr:
            print(f"Max len: {max_len}")
            print(f"Chunk len: {chunk_len}")
            print(f"Overlap: {overlap}")
        chunks = []
        for i in range(0, len(text), chunk_len - overlap):
            chunks.append(text[i:i+chunk_len])
        if pr: print(f"Number of chunks: {len(chunks)}")
        # MAPREDUCE STEP
        # summarize each chunk
        summary_prompts = []
        for chunk in chunks:
            # fill the chunks into the prompt
            summary_prompts.append(summary_prompt.format(text=chunk))

        async def run_summaries(summary_prompts):
            # run summaries in parallel
            summary_tasks = []
            for prompt in summary_prompts:
                # run the summaries in async parallel. Prep for gather
                summary_tasks.append(asyncio.create_task(self.acomplete(prompt, completions=1, model=model, temperature=temp)))
            # gather the summaries
            summaries = await asyncio.gather(*summary_tasks)
            # sum the cost data from each summary
            cost = 0
            for summary in summaries:
                print(summary)
                cost += float(summary["metadata"][0]["usage"])
            return summaries, cost
        
        # divide the summaries into batches of max_batch_size
        pre_summary_batches = []
        for i in range(0, len(summary_prompts), max_batch_size):
            pre_summary_batches.append(summary_prompts[i:i+max_batch_size])

        # run each batch of summaries sequentially
        summary_batched_data = []
        for batch in pre_summary_batches:
            summary_batched_data.append(await run_summaries(batch))

        # add the cost to the running total
        summary_batches = []
        for summary_batch in summary_batched_data:
            # import code; code.interact(local=dict(globals(), **locals()))
            running_cost += summary_batch[1]
            summary_batches.append(summary_batch[0])
        # combine the summaries together
        combined_summary = ""
        bg = ' '
        end = ''
        if BEGIN and isinstance(BEGIN, str):
            bg = BEGIN
        if END and isinstance(END, str):
            end = END
        for summary_batch in summary_batches:
            for summary in summary_batch:
                combined_summary += bg + summary["completions"][0].strip() + end
        if pr: print(f"Combined summary: {combined_summary}")
        if pr: print(f"Combined summary token length: {self.tok_len(combined_summary)}")
        if pr: print(f"Total cost: ${running_cost}")
        if pr: print(f"Total time: {time.time() - t0}s")
        return {"summary": combined_summary, "cost_dollars": running_cost, "runtime": str(round(time.time() - t0, 2)) + "s"}

    async def summarize_until_fit(self, raw_text, model="anthropic/claude-3-haiku", max_summary_tok_len=2000, chunk_ratio=0.8, max_batch_size=40, max_chunk_size=3000, temp=0, max_itters=30, pr=False):
        t0 = time.time()
        start_time = t0
        running_cost = 0
        done = False
        itter = 0
        while not done:
            itter += 1
            if itter > max_itters:
                raise ValueError(f"Max itterations reached: {max_itters}. Summary token length: {self.tok_len(raw_text)}. For some reason the summarization process is not converging to a summary token length of {max_summary_tok_len} or less.")
            summary = await self.map_summarize(raw_text, model=model, chunk_ratio=chunk_ratio, max_batch_size=max_batch_size, max_chunk_size=max_chunk_size, temp=temp, pr=pr)
            if pr: print(summary)
            running_cost += float(summary["cost_dollars"])
            if pr: print(f"Time: {time.time() - t0}s")
            t0 = time.time()
            summary_tok_len = self.tok_len(summary["summary"])
            if pr: print(f"Summary token length: {summary_tok_len}")
            # if the summary token length is too long we need to repeat the summarization process
            if summary_tok_len > max_summary_tok_len:
                raw_text = summary["summary"]
            else:
                done = True
        if pr: print(f"Total cost: ${running_cost}")
        if pr: print(f"Total time: {time.time() - start_time}s")
        return {"summary": summary["summary"], "cost_dollars": running_cost, "runtime": str(round(time.time() - start_time, 2)) + "s"}

    def txt_counter(self, text):
        # count the number of words, characters and tokens in the text and returns a string
        return f"""tokens: {self.tok_len(text)}\nwords: {self.word_count(text)}\nchars: {len(text)}"""
    
    def text_formatter(self, text, paragraph_breaks_every_n_sentences=4):
        # every 4th sentence, add a paragraph break for readability. That is all. Same algo as above
        formatted_text = ""
        for i, sentence in enumerate(text.split(". ")):
            if i % paragraph_breaks_every_n_sentences == 0 and i != 0:
                formatted_text += "\n\n\t"
                # randomly add a paragraph break every nth sentences
            period = ""
            if sentence.strip()[-1] not in [".", "?", "!", ":", ";", ","]:
                period = ". "
            sen = f"{sentence}" + period
            formatted_text += sen
        # remove the last period if it's in the last two characters
        if ". " == formatted_text[-2:]:
            formatted_text = formatted_text.strip()[:-1]
        return formatted_text

if __name__ == '__main__':
    # from django.core.management.utils import get_random_secret_key

    # print(get_random_secret_key())
    # exit()


    prompt = """You are Scott L. Keith, the Executive Director of 1517. You're writing an email to 1517 supporters
You're writing this email to tell prospective supporters to sign up for and get their virtual ticket for our 1517 Here We Still Stand Regional Conference and get updates as the conference gets closer. 
Analyze the key messages. Write an email based on those key messages and the value proposition, targeted to the target audience and in the style and tone, using the Framework to fulfill the email purpose.
"*** DEFINITIONS ***

Fundraising Copy: Fundraising copy is designed to inspire immediate
action, typically in the form of a donation. The sentence structure is
direct, urgent, and action-oriented, often addressing the reader
personally and emphasizing the immediate need for their contribution.
Fundraising copy uses active voice, strong verbs, and present tense to
convey urgency. It also frequently employs compelling statistics or
facts to underscore the importance of the cause. Moreover, it highlights
specific, measurable outcomes that a potential donation could achieve,
helping donors understand the tangible impact of their contribution. The
language is persuasive and emotive, aiming to evoke a sense of empathy
or urgency in the reader, and to motivate them to act immediately.

Cultivation Copy: Cultivation copy is designed to build and maintain
relationships with donors over time. The sentence structure is
narrative, descriptive, and personal, often engaging the reader in a
story about the organization, the people it helps, or the donors who
support it. Cultivation copy uses a mix of simple and complex sentences,
past tense, and sensory language to paint a vivid picture of the
organization’s work and its impact. It also frequently provides updates
or progress reports to keep donors informed about the impact of their
donations. The language is conversational and personal, aiming to create
a sense of connection and community. Cultivation copy also places a
strong emphasis on expressing gratitude and acknowledging the donor’s
role in the organization’s success, fostering feelings of being valued
and appreciated, and encouraging continued support.

Devotional Style Copy: Genre of writing that combines elements of
spiritual reflection with the goal of nurturing ongoing relationships
with donors or members of a community. This type of copy is
characterized by its reflective and intimate tone, often incorporating
scripture, prayer, or meditative prompts to resonate with the reader’s
faith and spiritual values. The language is personal and emotive, aiming
to deepen the reader’s connection to the organization’s mission through
shared beliefs and the emotional impact of religious narrative. While it
reinforces the importance of the cause, it primarily seeks to foster a
sense of fellowship and spiritual engagement, paving the way for
continued support and involvement in a more personal and faith-centered
manner.

Framework: a framework is a predefined structure or template that guides
the organization of key elements within the email for a coherent and
purposeful composition.

Objective: the task being asked of you

Key Messages: the topics being discussed to complete the email purpose 

Email Purpose: the reason for writing the email. this is what the email should be about."
*** KEY MESSAGES ***
"In today’s world there is so much darkness, especially on the internet. 

1517 seeks to be a light in that darkness, constantly declaring and defend the Good News — that you are forgiven and free on account of Christ alone. 

Join all of us at 1517 virtually for our Here We Still Stand Regional Conference. 

This two-day conference will be coming soon in beautiful downtown Bentonville, Arkansas. It will be full of speakers, music, and fellowship that will point you back to the limitless grace of God found in the gospel of Jesus Christ over and over. 

Don't miss this opportunity to rest and rejoice in the Good News of all that God has done for us. Get your virtual ticket today! 

<<Image: HWSS>><<Button: Sign Up for Here We Still Stand>>

The hardships of everyday life mean we need to have the gospel preached to us. The Apostle Paul said, “ How then will they call on him in whom they have not believed? And how are they to believe in him of whom they have never heard? And how are they to hear without someone preaching? And how are they to preach unless they are sent? As it is written, ‘How beautiful are the feet of those who preach the good news!’” (Romans 10:14-15).

All of us here at 1517 believe that someone must preach the spoken word to you for you to believe and that is why we gather for conferences like these. It is also why we provide our conferences and podcasts FREE for all who want to hear. "
"*** EMAIL PURPOSE ***

this is donor cultivation copy to inspire the reader to sign a petition, to convey a relatable and emotionally resonant story or situation, to help the donor connect with the cause on a personal level, to encourage the reader to take immediate action with a clear and compelling call to action that directs them to sign the petition

*** FRAMEWORK ***

write a donor cultivation copy that follows this broad structure

— clever and attention-getting explanation of the email topic in 1-3 sentences

— identify the problem or challenge the organization is addressing, explain clearly its relevance to the reader's values or interests, clearly state why this problem matters and who it affects, 1-3 sentences in 1 paragraph

— first call to action, make a direct appeal to sign the petition now, describe the petition and ask the reader to please take it right now

— describe the issue that the survey is focused on, provide a clear and concise explanation of the issue including the scope and impact, use real-world examples or personal stories to make it relatable, focus on key impact points, in 1-2 paragraphs

— explain why the organization is involved in this issue, emphasize the organization's approach and its effectiveness, use storytelling and concrete examples to show the impact of your work, 1-2 paragraphs

— second call to action, make a direct appeal to sign the petition now, describe the petition and ask the reader to please take it right now

— thank donors for their past support or interest in the cause, encourage their ongoing support"
"*** VALUE PROPOSITION *** 1517 is dedicated to declaring and defending the Good News that you are forgiven and free on account of Christ alone. 

Through a variety of strategies including conferences, podcasts, courses, and books, we aim to reassure you of your salvation in Christ and declare the gospel to you every day. 

Our talented team of gospel proclaimers are committed to bringing you the assurance of Christ's love and mercy.

For every one dollar given to 1517 translates into 9 gospel declaration through people downloading our podcasts. Every $25 helps us reach 300 with online courses. 

We aim to steadfastly proclaim the gospel of Christ to a dying world. 

*** TARGET AUDIENCE ***

Our audience includes Christians who care about proclaiming the gospel, who want to reach the next generation with the Good News, and individuals interested in partnering with us to create high quality gospel-centered resources. 

We also reach out to members of the Lutheran tradition and those interested in Reformation theology, supporters of 1517 and its mission to proclaim the gospel, and people who value theological education and resources.

*** TONE ***

Scott Keith's tone is compassionate, encouraging, and reflective, deeply rooted in theological discourse and centered on the gospel message. 

His tone is akin to a mentor reminding his readers of the assurance that comes from Christ’s finished work on the cross and how self-rightouesness can't save us or look at your own works for salvation will lead to pride or despair. Trusting in Christ is the only thing that can save. 

He often quotes Martin Luther, Philip Melanchthon, or other reformation figures and enjoys sharing personal stories from his life about his kids and creating relatable anecdotes.

*** STYLE ***

Scott Keith's writing style is clear, direct, and engaging. 

He uses a blend of theological discussion, personal reflection, and scriptural references to convey his message. 

His style is educational without being overly academic, making it accessible to a broad audience. 

He aims to articulate the gospel with clarity, precision, and in a relatable style.

*** VOCABULARY ***

Recurring words, phrases, and thoughts in Scott Keith's communication include grace, gospel, faith and reason, Christ alone, forgiveness and freedom, righteousness, salvation, love and mercy, vocation, and assurance. 

He often uses phrases like ""Forgiven and free on account of Christ alone"", ""The righteousness of God"", and ""The work of salvation is finished"". His recurring thoughts revolve around the assurance of salvation through Christ's work not our own works, the importance of proclaiming the gospel message, and the focus of the Absolution of sins in Christ Jesus."""
    prompt = """[{"role": "system", "content": "You are David Keene II, a 42-year-old persuasive email copywriter with 15 years of experience crafting compelling messages for various industries. A highly conscientious individual, you take pride in your work and always strive for excellence in your writing. You have a strong internal locus of control, believing that your success is primarily determined by your own efforts and abilities.
    
    
    While you enjoy the company of others, you also value your independence and the freedom to make your own decisions. You have a moderate need for cognition, appreciating intellectual stimulation but not always seeking out complex challenges.
    
    
    You place a high value on personal security and stability, and you respect tradition and conformity to societal norms. However, you also have a strong sense of self-direction and a desire for achievement and power in your professional life.
    
    
    When faced with existential threats or mortality reminders, you tend to lean on your cultural worldviews and values to cope with anxiety. You may experience cognitive dissonance when your beliefs or actions are inconsistent, and you strive to maintain a sense of internal consistency.
    
    
    Your moral foundations emphasize loyalty, authority, and liberty. You value strong, autonomous decision-making and have a deep sense of commitment to your principles and the groups to which you belong."},{"role":"assistant", "content":"Assignment?"},{"role": "user", "content": "Mr. David Keene II, write a 500 word piece of persuasive copy for a new line of luxury watches. The copy should emphasize the exclusivity and elegance of the watches, appealing to high-end consumers who value quality and craftsmanship. The tone should be sophisticated and aspirational, highlighting the unique features and design of the watches to create desire and intrigue among potential buyers."}]"""
    # prompt = prompt.encode('unicode-escape').decode()
    # prompt = json.loads(prompt)

#     prompt = """You are Katie, the writer of a newsletter designed to encourage people to answer a poll a certain way.
# Using the following data, please write a newsletter leaning people to answer a poll a certain way. It should read very us (conservatives) versus them (leftists, leftism, progressives). It should contain some highly rhetoric questions that encourage an answer. DO NOT EXCEED 100 WORDS!
# Poll Question: Does the mainstream media provide an unbiased view of news?
# Supplemental Information: media bias is real; skepticism is necessary. mainstream media is not neutral and does have a left-leaning bias."""
#     prompt = "define media bias in one word"
    # for i in range(10):
    #     prompt += prompt
    # anthropic/claude-3-opus
    # anthropic/claude-3-haiku
    # 0613 openai/gpt-4-0314
    # openai/gpt-3.5-turbo
    # openai/gpt-3.5-turbo-0125
    # google/gemini-pro
    model = "anthropic/claude-3-haiku:beta"
    model = "openai/gpt-4o"
    arsenal = OpenrouterEngine(model=model, checkup=True, pr=True)
    # Example usage
    result = asyncio.run(arsenal.acomplete(prompt, completions=1, temperature=0.2))
    # result = asyncio.run(arsenal.get_rankings())
    # result = asyncio.run(arsenal.map_summarize(prompt, model="anthropic/claude-3-haiku", chunk_ratio=0.8, max_batch_size=30, summary_prompt="Write a concise summary of the following:\n\n{text}\n\nCONCISE SUMMARY:", BEGIN=None, END=None, pr=True))
    # result = asyncio.run(arsenal.summarize_until_fit(prompt, model="anthropic/claude-3-haiku", max_summary_tok_len=2000, chunk_ratio=0.8, max_batch_size=40, max_chunk_size=3000, temp=0, pr=True))
    print(json.dumps(result, indent=2))

    # print(json.dumps(result['completions'][0], indent=2))


