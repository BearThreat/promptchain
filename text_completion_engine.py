
from langchain.prompts import PromptTemplate
from langchain.chains.llm import LLMChain
from langchain.schema import HumanMessage, LLMResult
if __name__ == "__main__":
    from pathlib import Path
    from dotenv import load_dotenv
    env_path = Path('.') / '.env'
    load_dotenv(dotenv_path=env_path)
from typing import List
import os, re, difflib, asyncio, time, tiktoken, certifi, datetime, copy, json
import openai
# from langchain.callbacks import get_openai_callback
# from langchain.chat_models import ChatOpenAI
from langchain_community.callbacks import get_openai_callback
# from langchain_community.chat_models import ChatOpenAI
from langchain_openai import ChatOpenAI
from langchain.callbacks.base import AsyncCallbackHandler, BaseCallbackHandler
os.environ['SSL_CERT_FILE'] = certifi.where()
import nltk, spacy

nlp = spacy.load("en_core_web_sm")
# python -m spacy download en_core_web_sm

# sample = {'nltk': {"sub_sample1": "value1", "sub_sample2": "value2"}}
# print(json.dumps(sample, indent=4))


# import the type annotations
from typing import Dict, List, Any

class MyCustomAsyncHandler(AsyncCallbackHandler):
    def __init__(self):
        super().__init__()
        self.token_buffers = {}
        self.primary_buffer = None
        # start a timer
        self.start_time = time.time()

    async def on_llm_new_token(self, token: str, run_id, parent_run_id, **kwargs) -> None:
        # Ensure there is a buffer for the parent_run_id
        if parent_run_id not in self.token_buffers:
            self.token_buffers[parent_run_id] = ''

        # Append the new token to the buffer for the parent_run_id
        self.token_buffers[parent_run_id] = self.token_buffers[parent_run_id] + token

        if parent_run_id != self.primary_buffer:
            # If the parent_run_id is not the primary buffer
            return
        # every 10 seconds, print the tokens
        if time.time() - self.start_time > 0.2 and self.token_buffers[parent_run_id] != '':
            print(f"{self.token_buffers[parent_run_id]}", end='')
            self.start_time = time.time()
            # empty the buffer
            self.token_buffers[parent_run_id] = ''

    async def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], parent_run_id, **kwargs: Any
    ) -> None:
        """Run when chain starts running."""
        if self.primary_buffer is None:
            self.primary_buffer = parent_run_id
        # print("zzzz....")
        # await asyncio.sleep(0.3)
        # print("Hi! I just woke up. Your llm is starting")

    async def on_llm_end(self, response: LLMResult, parent_run_id, **kwargs: Any) -> None:
        """Run when chain ends running."""
        if parent_run_id != self.primary_buffer:
            # If the parent_run_id is not the primary buffer
            return
        # print primary buffer
        print(f"{self.token_buffers[parent_run_id]}", end='')
        print("zzzz....")
        await asyncio.sleep(0.3)
        print("Hi! I just woke up. Your llm is ending")



def word_count(text):
    def accurate_word_count(text):
        # split text into sentences
        try:
            doc = nlp(text)
            sentences = [sent.text.strip() for sent in doc.sents]
        except Exception as e:
            sentences = nltk.sent_tokenize(text)
            print(e)
        # count the words in each sentence
        word_count = 0
        for i, sentence in enumerate(sentences):
            try:
                # Ensure sentence is a string
                if not isinstance(sentence, str):
                    sentence = str(sentence)
                words = re.findall(r'\b\w+\b', sentence)
                word_count += len(words)
            except Exception as e:
                word_count += len(nltk.word_tokenize(sentence))
                print(e)
        return word_count
    return str(accurate_word_count(text))


class TextCompletionEngine():
    def __init__(self, prompt=None, model_name="gpt-4", temp=0.05, completions=1, timeout=None, **kwargs) -> str:
        # download the punkt tokenizer. First check if it's already downloaded
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt')
        self.model_name = model_name
        self.temp = temp
        self.cost_dollars = 0
        if timeout:
            self.timeout = timeout
            self.allow_dynamic_timeout = False
        else:
            self.allow_dynamic_timeout = True
            
        if isinstance(prompt, str):
            self.prompt = prompt
            self.run_prompt(self.prompt, completions=completions, **kwargs)
    
    def dynamic_timeout(self, prompt_token_len):
        # this func is pessimistic. It assumes the worst case scenario for the timeout
        if self.allow_dynamic_timeout:
            if self.model_name.endswith("-preview") and self.model_name.startswith("gpt-4-"):
                tps = 225 / 22
                self.timeout = 4000 * 1/tps  # max completion tokens is 4000
            elif self.model_name == "gpt-4-1106-preview" or \
                self.model_name == "gpt-4-vision-preview":
                tps = 225 / 22
                self.timeout = 4000 * 1/tps  # max completion tokens is 4000
            elif self.model_name.startswith("gpt-3.5-turbo-16k") or \
                self.model_name.startswith("gpt-3.5-turbo-1106"):
                tps = 3638 / 290  # tokens per second
                self.timeout = min(16000 - int(prompt_token_len), 4000) * 1/tps
            elif self.model_name.startswith("gpt-4-32k"):
                tps = 359 / 90  # assuming it's twice as slow as gpt-4
                self.timeout = (32000 - int(prompt_token_len)) * 1/tps
            elif self.model_name.startswith("gpt-4"):
                tps = 586 / 22  # calculated from previous completion tokens for a job
                self.timeout = (8000 - int(prompt_token_len)) * 1/tps
            elif self.model_name.startswith("gpt-3.5-turbo"):
                tps = 3121 / 135  
                self.timeout = (4000 - int(prompt_token_len)) * 1/tps  # 1/tps is seconds per token
            else:
                self.timeout = 180

            self.timeout = int(self.timeout)
            if self.timeout < 10:
                self.timeout = 10

    async def run_prompt(self, prompt, prompt_variables=None, completions=1, **kwargs):
        return await self.acomplete(prompt, prompt_variables, completions=completions, **kwargs)
    
    # def arun_prompt(self, prompt, prompt_variables=None, completions=1):
    #     return self.acomplete(prompt, prompt_variables, completions=completions)
    
    # def complete(self, partial_template, prompt_variables, completions):
    #     return asyncio.run(self.acomplete(partial_template, prompt_variables, completions))

    def construct_prompt_from_template(self, template: str) -> str:
        # constructs a langchain prompt from a template and input variables

        # handle stray curly braces
        def remove_dollar_braces(match):
            return f'${match.group(1)}'
        template = re.sub(r'\$\{([^\{\}]+)\}', remove_dollar_braces, template)
        # make sure there are no single non matching instances of { or } in the template
        if template.count('{') != template.count('}'):
            # temporarily replace curly braces that are paired (e.g. { some text }) with a placeholder
            # we'll use $$$ for { and @@@ for }
            # remember. we're only doing this for PAIRED curly braces because we want to identify stray curly braces
            # First, let's find all pairs of matching curly braces
            matches = re.findall(r'\{.*?\}', template)

            # Now, replace these matched pairs with placeholders
            for match in matches:
                template = template.replace(match, match.replace('{', '$$$').replace('}', '@@@'))

            # At this point, any remaining '{' or '}' are unpaired. We can handle them as needed.
            # For example, we could remove them:
            template = template.replace('{', '').replace('}', '')

            # Finally, replace the placeholders back to their original characters
            for match in matches:
                template = template.replace('$$$', '{').replace('@@@', '}')

        # first need to infer the input variables from the template
        input_variables = self.infer_input_variables(template=template)
        # then need to construct the prompt from the template and input variables
        prompt = PromptTemplate(template=template, input_variables=input_variables)
        # prompt = template.format(**{input_variable: f"{{{input_variable}}}" for input_variable in input_variables})
        return prompt
    
    def remove_template_vars_and_brackets(self, template):
        # handle stray curly braces
        def remove_dollar_braces(match):
            return f'${match.group(1)}'
        template = re.sub(r'\$\{([^\{\}]+)\}', remove_dollar_braces, template)
        # make sure there are no single non matching instances of { or } in the template
        if template.count('{') != template.count('}'):
            # temporarily replace curly braces that are paired (e.g. { some text }) with a placeholder
            # we'll use $$$ for { and @@@ for }
            # remember. we're only doing this for PAIRED curly braces because we want to identify stray curly braces
            # First, let's find all pairs of matching curly braces
            matches = re.findall(r'\{.*?\}', template)

            # Now, replace these matched pairs with placeholders
            for match in matches:
                template = template.replace(match, match.replace('{', '$$$').replace('}', '@@@'))

            # At this point, any remaining '{' or '}' are unpaired. We can handle them as needed.
            # For example, we could remove them:
            template = template.replace('{', '').replace('}', '')

            # Finally, replace the placeholders back to their original characters
            for match in matches:
                template = template.replace('$$$', '{').replace('@@@', '}')
        return template

    @staticmethod
    def infer_input_variables(template: str) -> List[str]:
        # Regular expression pattern to match input variables enclosed in single curly braces
        pattern = re.compile(r'(?<![$\{])\{([^\{\}]+)\}(?!\})')
        # Find all input variables using the regex pattern
        input_variables = re.findall(pattern, template)
        # Return only unique variable names
        return list(set(input_variables))
    
    def tok_len(self, text: str) -> int:
        return len(tiktoken.encoding_for_model(self.model_name).encode(str(text)))
    
    # cut off first n tokens
    def cut_first_n(self, text: str, n: int) -> str:
        if not isinstance(text, str):
            text = str(text)
        enc = tiktoken.encoding_for_model(self.model_name)
        encoded_text = enc.encode(text)[n:]
        return str(enc.decode(encoded_text))
    
    def keep_last_n(self, text: str, n: int) -> str:
        if not isinstance(text, str):
            text = str(text)
        enc = tiktoken.encoding_for_model(self.model_name)
        try:
            encoded_text = enc.encode(text)[-n:]
        except IndexError:
            encoded_text = enc.encode(text)
        return str(enc.decode(encoded_text))
    
    def fit_in_context_window(self, text: str, percent: float) -> str:
        # percent = max percent of model context length to use
        # keep the last n percent of the max context length
        if not isinstance(text, str):
            text = str(text)
        enc = tiktoken.encoding_for_model(self.model_name)
        max_len = self.context_len()
        # make sure percent is between 0 and 1
        if percent > 1: percent = 1
        if percent < 0: percent = 0
        n = int(max_len * percent)  # max tokens to keep
        # this only applies when the text is longer than the max context length times the percent
        encoded_text = enc.encode(text)
        if len(encoded_text) > n:
            encoded_text = encoded_text[-n:]
            return str(enc.decode(encoded_text))
        else:
            return text
        
    def combine_and_force_fit(self, text1: str, text2: str, return_tuples=False) -> str:
        # find tok len of text1 and then trim text2 so that text1 + text2 is less than the max context length
        # if text1 is longer than the max context length then trim to the max context length and return text1
        # if text1 + text2 is less than the max context length then return text1 + text2
        # find the tok len of text1
        tok_len_text1 = self.tok_len(text1)
        if tok_len_text1 >= self.context_len():
            # trim text1 to the max context length
            text1 = self.keep_last_n(text1, self.context_len())
            if return_tuples:
                return text1, ""
            return text1
        else:
            # trim text2 so that text1 + text2 is less than the max context length
            tok_len_text2 = self.tok_len(text2)
            if tok_len_text1 + tok_len_text2 >= self.context_len():
                # trim text2
                text2 = self.keep_last_n(text2, (self.context_len() - tok_len_text1))
            if return_tuples:
                return text1, text2
            return text1 + text2
        
    def trim_by_importance(self, texts: List[str], reserved_tokens: int) -> List[str]:
        # trim the texts by importance. The most important text is the first text in the list
        # start by combining all the texts and then trim the combined text starting with the least important text
        # reserved_tokens is the number of tokens to remove from the context window length. It's typically the prompt token length
        none_list = []
        while True:
            combined_text = ''.join(texts)
            # find the tok len of the combined text
            tok_len_combined_text = self.tok_len(combined_text)
            if tok_len_combined_text <= self.context_len() - reserved_tokens:
                # we're done
                return texts + none_list
            else:
                # trim the least important text by n tokens where n is the difference between the tok len of the combined text and the max context length
                # if n is greater than the tok len of the least important text then remove the least important text from the list
                if self.tok_len(texts[-1]) > tok_len_combined_text - (self.context_len() - reserved_tokens):
                    # replace the least important text with an empty string
                    del texts[-1]
                    none_list.append("")
                else:
                    # trim the least important text
                    texts[-1] = self.cut_first_n(texts[-1], tok_len_combined_text - (self.context_len() - reserved_tokens))
                    # and we're done
                    return texts + none_list
    
    def context_len(self) -> int:
        # return the context length of a model
        if self.model_name == "gpt-4" or \
            self.model_name == "gpt-4-0613":
            return 8000
        elif self.model_name == "gpt-3.5-turbo" or\
            self.model_name == "gpt-3.5-turbo-instruct":
            return 4000
        elif self.model_name == "gpt-3.5-turbo-16k" or \
            self.model_name == "gpt-3.5-turbo-1106" or \
            self.model_name == "gpt-3.5-turbo-0125":
            return 16000
        elif self.model_name == "gpt-4-32k" or \
            self.model_name == "gpt-4-32k-0613":
            return 32000
        elif self.model_name == "gpt-4-1106-preview" or \
            self.model_name == "gpt-4-vision-preview" or \
            self.model_name == "gpt-4-turbo-preview" or \
            self.model_name == "gpt-4-0125-preview":
            return 128000
        else:
            raise ValueError("Unknown model context length for model: " + self.model_name)
        
    def construct_combined_message(self, result_dict, sep) -> str:
        combined_message_parts = []
        prev_user = None
        # result_dict is a dictionary of dictionaries where the keys are timestamps 
        # the values are dictionaries with at least a 'message' key. 
        for ts, content in sorted(result_dict.items(), key=lambda x: float(x[0])):
            real_name = content.get('real_name', None)
            if 'message' not in content:
                raise ValueError("result_dict must contain a 'message' key")
            message = content['message']
            if real_name:
                if real_name == prev_user:
                    part = '\n' + message
                else:
                    part = sep + real_name + ':\n' + message
            else:
                part = sep + message

            combined_message_parts.append(part)
            prev_user = real_name

        combined_message = ''.join(combined_message_parts)
        return combined_message
    
    def trim_content(self, result_dict, token_limit, sep = '\n\n'):
        trimmed_dict = result_dict.copy()
        combined_message = self.construct_combined_message(trimmed_dict, sep=sep)
        total_tokens = self.tok_len(combined_message)
        # print(f"total tokens: {total_tokens}")
        # print(f"token limit: {token_limit}")
        # import code; code.interact(local=dict(globals(), **locals()))
        while total_tokens > token_limit:
            # Get the key for the first message in trimmed_dict
            first_key = sorted(trimmed_dict.keys())[0]
            first_message = trimmed_dict[first_key]['message']
            # Cut 200 tokens from the first message, or remove it if fewer than 200 tokens remain
            if self.tok_len(first_message) > 200:
                new_message = self.cut_first_n(first_message, 200)
                trimmed_dict[first_key]['message'] = new_message
            else:
                del trimmed_dict[first_key]
            # Reconstruct the combined message and recheck the token length
            combined_message = self.construct_combined_message(trimmed_dict, sep=sep)
            total_tokens = self.tok_len(combined_message)
        return combined_message
    
    def create_template(self, meta_template_path, template_selections, prompt_variables, model_dict):
        template = self.article_copy_meta_template_builder(meta_template_path, template_selections, model_dict)
        # find the token length of the template. Need to remove all content inside and including the {...} placeholders without changing template
        def fill_template_vars(template, prompt_vars):
            for key, value in prompt_vars.items():
                value = value.replace('_', ' ')
                template = template.replace('{' + key + '}', value)
            return template
        template = fill_template_vars(template, prompt_variables)
        self.prompt_token_len = self.tok_len(template)
        
        template = re.sub(r'\{.*?\}', '', template)
        return template

    async def acomplete(self, partial_template, prompt_variables, completions, min_completion_token_space=None, **kwargs):
        # print(partial_template)
        # print(prompt_variables)
        # find the token length of the template. Need to remove all content inside and including the {...} placeholders without changing template
        def fill_template_vars(partial_template, prompt_vars):
            for key, value in prompt_vars.items():
                value = value.replace('_', ' ')
                partial_template = partial_template.replace('{' + key + '}', value)
            return partial_template
        if isinstance(prompt_variables, dict):
            filled_template = fill_template_vars(partial_template, prompt_variables)
            template = re.sub(r'\{.*?\}', '', filled_template)
        else:
            prompt_variables = dict()
            template = partial_template
            template = template.replace('{', '[').replace('}', ']')  # replace curly braces with square brackets to avoid openai key error

        # for every remaining {...} placeholder, replace it with a blank string
        self.prompt_token_len = self.tok_len(template)
        # import code; code.interact(local=dict(globals(), **locals()))
        if min_completion_token_space:
            # if the prompt token len is more than the model's context window len then we need to trim the prompt and leave at least truncation_completion_max_tok_len tokens
            if self.prompt_token_len + min_completion_token_space > self.context_len():
                template = self.fit_in_context_window(template, (self.context_len() - min_completion_token_space) / self.context_len())

        # import code; code.interact(local=dict(globals(), **locals()))
        # for every remaining {...} placeholder, replace it with a blank string
        self.prompt_token_len = self.tok_len(template)
        # print(template)
        prompt = self.construct_prompt_from_template(template)


        self.dynamic_timeout(self.prompt_token_len)
        print(f"timeout: {self.timeout}")
        # import code; code.interact(local=dict(globals(), **locals()))
        self.llm = ChatOpenAI(model_name=self.model_name, 
                                         temperature=self.temp, 
                                         request_timeout=self.timeout, 
                                         streaming=True,
                                         callbacks=[MyCustomAsyncHandler()],
                                         **kwargs)  # , logit_bias={"25": -100,}, max_tokens=1)
        # from langchain.chat_models import ChatOpenAI
        # self.llm = ChatOpenAI(model_name=self.model_name, temperature=self.temp, 
        #                       request_timeout=self.timeout, logit_bias={"25": -100,
        #                                                                 "7479": -100,
        #                                                                 "77": -100,
        #                                                                 "12915": -100,})
        # from langchain.llms import OpenAI

        # self.llm = OpenAI(model_name=self.model_name, temperature=self.temp, 
        #                       request_timeout=self.timeout, logit_bias={"24": -100})
        # import code; code.interact(local=dict(globals(), **locals()))
        article_chain = LLMChain(prompt=prompt, llm=self.llm, output_key="llm_response")
        # import code; code.interact(local=dict(globals(), **locals()))
        
        async def async_generate(chain, responses):
            # print(prompt_variables)
            resp = await chain.apredict(**prompt_variables)
            cost = self.cost(self.prompt_token_len, self.tok_len(resp))
            responses.append({"response": resp, "metadata": {"characters": f"{len(resp)}", 
                                                             "tokens": f"{str(self.tok_len(resp) + self.prompt_token_len)}", 
                                                             "returned_tokens": f"{str(self.tok_len(resp))}",
                                                             "words": f"{word_count(resp)}", 
                                                             "cost_dollars": f"{str(round(float(cost), 6))}"}})

        async def generate_concurrently(chain, callback):
            responses = []
            tasks = [async_generate(chain, responses) for _ in range(completions)]
            await asyncio.gather(*tasks)
            total_tokens = sum([int(resp["metadata"]["tokens"]) for resp in responses])
            total_returned_tokens = sum([int(resp["metadata"]["returned_tokens"]) for resp in responses])
            # total_tokens = self.prompt_token_len*completions + total_returned_tokens
            job_cost = self.cost(self.prompt_token_len*completions, total_returned_tokens)
            prompt = fill_template_vars(template, prompt_variables)
            return {"completions": responses, "prompt": prompt, "prompt_variables": prompt_variables, "meta_data": {
                                                         "runtime": None, # will be a number in seconds
                                                         "temperature": self.temp,
                                                         "completions": completions,"total_tokens": total_tokens, 
                                                        #  "global_prompt_tokens": self.prompt_token_len*completions,
                                                        #  "global_completion_tokens": callback.total_tokens - self.prompt_token_len*completions,
                                                         "prompt_token_len": self.prompt_token_len,
                                                         "completion_token_avg": int(total_returned_tokens/completions),
                                                         # round to 6 decimal places
                                                         "cost_dollars": str(round(float(job_cost), 6)),}}
        t0 = time.time()
        with get_openai_callback() as cb:
            try:
                result = await generate_concurrently(article_chain, cb)
            except Exception as e:
                # print(e)
                # import code; code.interact(local=dict(globals(), **locals()))
                raise e
        # set the runtime in the meta_data
        result["meta_data"]["runtime"] = time.time() - t0
        # round the runtime to 2 decimal places
        result["meta_data"]["runtime"] = str(round(result["meta_data"]["runtime"], 2)) + "s"
        # add the cost to the running total
        self.cost_dollars += float(result["meta_data"]["cost_dollars"])
        return result
    
    def cost(self, prompt_tokens, completion_tokens):
        if self.model_name.startswith("gpt-4-") and self.model_name.endswith("-preview"):
            prompt_cost = 0.01 * (prompt_tokens / 1000)
            completion_cost = 0.03 * (completion_tokens / 1000)
        elif self.model_name == "gpt-4" or \
            self.model_name == "gpt-4-0613":
            prompt_cost = 0.03 * (prompt_tokens / 1000)
            completion_cost = 0.06 * (completion_tokens / 1000)
        elif self.model_name == "gpt-4-32k" or \
            self.model_name == "gpt-4-32k-0613":
            prompt_cost = 0.06 * (prompt_tokens / 1000)
            completion_cost = 0.12 * (completion_tokens / 1000)
        elif self.model_name == "gpt-3.5-turbo-0125":
            prompt_cost = 0.0005 * (prompt_tokens / 1000)
            completion_cost = 0.0015 * (completion_tokens / 1000)
        elif self.model_name == "gpt-3.5-turbo-1106":
            prompt_cost = 0.001 * (prompt_tokens / 1000)
            completion_cost = 0.002 * (completion_tokens / 1000)
        elif self.model_name == "gpt-3.5-turbo" or \
            self.model_name == "gpt-3.5-turbo-0613" or \
                self.model_name == "gpt-3.5-turbo-instruct":
            prompt_cost = 0.0015 * (prompt_tokens / 1000)
            completion_cost = 0.002 * (completion_tokens / 1000)
        elif self.model_name == "gpt-3.5-turbo-16k":
            prompt_cost = 0.003 * (prompt_tokens / 1000)
            completion_cost = 0.004 * (completion_tokens / 1000)
        elif self.model_name == "text-embedding-ada-002":
            prompt_cost = 0.0001 * (prompt_tokens / 1000)
            completion_cost = 0.0001 * (completion_tokens / 1000)
        else:
            raise ValueError("Invalid model name")
        total_cost = prompt_cost + completion_cost
        return total_cost


if __name__ == "__main__":
    text = """Can you please repeat the text back to me verbatim?\n\n Document:\n    Fellow American,\n\nOur Republic is under attack. The very foundation of our democracy is at risk, and we cannot stand idly by. The misuse of the 14th Amendment to remove qualified candidates from the ballot is a threat we cannot ignore.\n\nImagine a future where the voices of the people are silenced, where only a select few decide who can run for office. This is the reality we face if we allow this egregious misuse of the 14th Amendment to continue.\n\nAlready, lawsuits have been filed to keep Donald Trump off the 2024 ballot. This is not about political differences or disagreements. This is about radical interest groups using the Constitution as a weapon to silence those they do not agree with.\n\nDr. Cornell West, Robert F. Kennedy, and others are also potential targets of this assault on our democracy. We cannot let this stand.\n\nThat is why USJF is taking action. Through our Election Integrity Task Force, we will closely monitor these states and provide support to top state election officials. We will file Constitutional Law Briefs in the districts where court action is taking place. We will fight for the integrity of our elections.\n\nWe cannot allow our Republic to become a Banana Republic, where there is only one choice for the people. We must preserve the principles of discourse and differences of opinions that give our voters a say in who will lead them.\n\nFellow American, I know you wouldn\'t fall for this assault on our democracy. I know we can count on you to stand with us in this fight. Together, we can protect the integrity of our elections and ensure that our Republic remains strong.\n\nSincerely,\n\n[Your Name]\n    Urgent Problem Statement:\n\nThe misuse of the 14th Amendment to remove candidates from the ballots is a grave threat to our democracy. It is absurd and astounding that this amendment, originally intended to prevent members of the Confederacy from taking office, is now being twisted to keep any candidate that radical interest groups disagree with off the ballot. This misuse is driven solely by a disagreement with the viewpoints and policy ideas of these candidates.\n\nAlready, several organizations have filed lawsuits to keep qualified candidates like Donald Trump off the 2024 ballot using Article 14, Sec. 3 of the Constitution. This disqualification clause, written after the Civil War, was meant to prevent individuals who engaged in insurrection or provided aid to insurrectionists from running for office. However, it is now being weaponized to silence candidates who may not align with certain political agendas.\n\nDr. Cornell West, Robert F. Kennedy, Donald Trump, and others are all potential targets of this egregious misuse of the 14th Amendment. We cannot allow our Republic to be undermined in this way. The United States Justice Foundation (USJF) is taking action through our Election Integrity Task Force. We will closely monitor the states where these lawsuits are being filed and provide letter briefs to the top state election officials. Additionally, we will file Constitutional Law Briefs in the districts where court action is taking place.\n\nWe must not let our Republic devolve into a Banana Republic where there is only one choice for the people. It is crucial that we allow for discourse and differences of opinions to ensure our voters have a say in who will lead them. Join us in standing against this threat to our democracy.\n    Call to Action for Support and Donation:\n\nWe need your help now more than ever. The threat to our Republic is real, and we cannot let it go unchallenged. Your support is crucial in our fight to protect our democracy and ensure that every qualified candidate has a fair chance to be on the ballot.\n\nWithout your financial donations, we simply cannot continue our mission. We rely on the generosity of patriots like you to fund our efforts and make a difference. Your contribution will enable us to intervene in the misuse of the 14th Amendment, advocate for election integrity, and stand up against those who seek to silence opposing viewpoints.\n\nJoin us in this urgent battle to preserve our democracy. Your support is how we can stay in the fight and make a lasting impact. Together, we can prevent our Republic from turning into a Banana Republic, where there is only one choice for the people.\n\nI know we can count on you to stand with us. Your donation will make a difference and help us protect the rights of all Americans. Please, don\'t wait. Donate now and be a part of the solution.\n\nThank you for your unwavering support.\n\nSincerely,\n\n[Your Name]\n    Key Messages:\n\nDon\'t let them keep Donald Trump or other qualified candidates off the ballot.\n\nThe absurdity surrounding the misuse of the 14th Amendment is astounding. The 14th Amendment was added to the Constitution after the Civil War specifically to prevent members of the Confederacy from taking office. Now, they are trying to use it to keep any candidate radical interest groups don\'t want on the ballot. Simply because they do not agree with those candidates\' viewpoints or policy ideas.\n\nSeveral organizations have already filed lawsuits in courts trying to keep Donald Trump off of the 2024 ballot using Article 14, Sec. 3, which is a disqualification clause written specifically after the Civil War. This clause states that no person who has already taken an oath of office to high offices such as congressional and presidential, who has engaged in insurrection, or given aid or comfort to those who have, can be disqualified from running for office. There is an opposing candidate who is also filing suits to advocate for removing people from the ballot who may not agree with their policy.\n\nDr. Cornell West (independent), Robert F. Kennedy (independent), Donald Trump (Republican), and others are all potential targets of this egregious misuse of the 14th Amendment.\n\nWe cannot let this threat to our Republic continue. USJF will intervene in this effort through the Election Integrity Task Force by closely monitoring these states and plan to go to every one of these states, providing letter briefs to the top state election officials. We are also going to file Constitutional Law Briefs in the districts where there is court action on this.\n\nWe cannot let our Republic turn into a Banana Republic by creating an election where there is only one choice for people. We have to allow for discourse and differences of opinions to give our voters a say in who will lead them.\n\nFramework:\n4. Background of the Organization:\n- Overview of organization\'s history and mission. Use the overview for these details.\n- Emphasize why this mission is important. We are trying to save our democracy.\n\nStyle -\n- Vary the sentence and paragraph lengths in a VISUALLY PLEASING way to keep the reader\'s attention\n- 8TH GRADE READING LEVEL\n- Use of ALL CAPS to emphasize key details and emotive language.\n- Be alarmist. Convention of States Action, we are working overtime to convince the required 34 state legislatures to call for an Article V convention to place limits on the power and jurisdiction of the federal government\n- While maintaining an alarmist tone, ensure to balance it with positivity and hope to inspire action.\n- On a scale of 1-5, where 5 is very informal and 1 is very formal, make the tone a 4.\n- On a scale of 1-5, where 5 is very alarmist and 1 is not alarmist, make the tone a 5\n- Use flattering and persuasive language to create an us versus them type situation. "I know you wouldn\'t fall for this", "I know we can count on you"\n- DO NOT COMPLETE AN ENTIRE LETTER. THIS SHOULD ONLY BE A SECTION\n\nEnsure the section follows these preferences:\n\nPreference:\nDo not use dues and/or membership. Use the word sponsorship if needed.\nPrefers Keystone XL pipeline (not Pipeline).\nNo the before USJF unless absolutely necessary.\nOBAMACARE all uppercase\nDon\'t use the word crack as in our crack legal team\nCapitalize Communist, Constitutional\nEliminate the terms liberal or liberals they prefer leftists, extremists, radicals, leftist elites, or usurpers.\nDo not use retired EVER when referring to J.D. You can use former or as a six-term representative\nChange Fraud to Integrity or Law Election Integrity Task Force or Election Law Task Force (prefer Law as on their website, but either is acceptable)\nNon-citizen (hyphenated)\nALWAYS BEGIN A LETTER WITH THE WORD YOU NEVER WITH I\nNEVER USE MIGRANTS OR IMMIGRATION WHEN DISCUSSING OUR OPEN BORDER! illegal aliens, illegal immigration, and/or foreign invasion are preferred.\nAlways keep conservative lowercase.\nNever use My friend\n    Key Messages:\n\nDon\'t let them keep Donald Trump or other qualified candidates off the ballot.\n\nThis proposed mail package will talk about the misuse of the 14th Amendment to remove candidates from the ballots.\n\nThe absurdity surrounding the misuse of the 14th Amendment is astounding. The 14th Amendment was added to the Constitution after the Civil War specifically to prevent members of the Confederacy from taking office. Now, they are trying to use it to keep any candidate radical interest groups don\'t want on the ballot. Simply because they do not agree with those candidates\' viewpoints or policy ideas.\n\nSeveral organizations have already filed lawsuits in courts trying to keep Donald Trump off of the 2024 ballot using Article 14, Sec. 3, which is a disqualification clause written specifically after the Civil War. This clause states that no person who has already taken an oath of office to high offices such as congressional and presidential, who has engaged in insurrection, or given aid or comfort to those who have, can be disqualified from running for office. There is an opposing candidate who is also filing suits to advocate for removing people from the ballot who may not agree with their policy.\n\nDr. Cornell West (independent), Robert F. Kennedy (independent), Donald Trump (Republican), and others are all potential targets of this egregious misuse of the 14th Amendment.\n\nWe cannot let this threat to our Republic continue. USJF will intervene in this effort through the Election Integrity Task Force by closely monitoring these states and plan to go to every one of these states, providing letter briefs to the top state election officials. We are also going to file Constitutional Law Briefs in the districts where there is court action on this.\n\nWe cannot let our Republic turn into a Banana Republic by creating an election where there is only one choice for people. We have to allow for discourse and differences of opinions to give our voters a say in who will lead them.\n\nFramework:\n5. Impact of the Organization\'s Efforts:\n- Description of the impact of the organization\'s work.\n- Examples of how it\'s worked, ignore this requirement if there are no examples\n- Illustration of the national scope of the issue, highlighting its emergency status.\n\nStyle -\n- Vary the sentence and paragraph lengths in a VISUALLY PLEASING way to keep the reader\'s attention\n- 8TH GRADE READING LEVEL\n- Use of ALL CAPS to emphasize key details and emotive language.\n- Be alarmist. Convention of States Action, we are working overtime to convince the required 34 state legislatures to call for an Article V convention to place limits on the power and jurisdiction of the federal government\n- While maintaining an alarmist tone, ensure to balance it with positivity and hope to inspire action.\n- On a scale of 1-5, where 5 is very informal and 1 is very formal, make the tone a 4.\n- On a scale of 1-5, where 5 is very alarmist and 1 is not alarmist, make the tone a 5\n- Use flattering and persuasive language to create an us versus them type situation. "I know you wouldn\'t fall for this", "I know we can count on you"\n- DO NOT COMPLETE AN ENTIRE LETTER. THIS SHOULD ONLY BE A SECTION\n\nEnsure the section follows these preferences:\n\nPreference:\nDo not use dues and/or membership. Use the word sponsorship if needed.\nPrefers Keystone XL pipeline (not Pipeline).\nNo the before USJF unless absolutely necessary.\nOBAMACARE all uppercase\nDon\'t use the word crack as in our crack legal team\nCapitalize Communist, Constitutional\nEliminate the terms liberal or liberals they prefer leftists, extremists, radicals, leftist elites, or usurpers.\nDo not use retired EVER when referring to J.D. You can use former or as a six-term representative\nChange Fraud to Integrity or Law Election Integrity Task Force or Election Law Task Force (prefer Law as on their website, but either is acceptable)\nNon-citizen (hyphenated)\nALWAYS BEGIN A LETTER WITH THE WORD YOU NEVER WITH I\nNEVER USE MIGRANTS OR IMMIGRATION WHEN DISCUSSING OUR OPEN BORDER! illegal aliens, illegal immigration, and/or foreign invasion are preferred.\nAlways keep conservative lowercase.\nNever use My friend\n    Key Messages:\n\nDon\'t let them keep Donald Trump or other qualified candidates off the ballot.\n\nThis proposed mail package will talk about the misuse of the 14th Amendment to remove candidates from the ballots.\n\nThe absurdity surrounding the misuse of the 14th Amendment is astounding. The 14th Amendment was added to the Constitution after the Civil War specifically to prevent members of the Confederacy from taking office. Now, they are trying to use it to keep any candidate radical interest groups don\'t want on the ballot. Simply because they do not agree with those candidates\' viewpoints or policy ideas.\n\nSeveral organizations have already filed lawsuits in courts trying to keep Donald Trump off of the 2024 ballot using Article 14, Sec. 3, which is a disqualification clause written specifically after the Civil War. This clause states that no person who has already taken an oath of office to high offices such as congressional and presidential, who has engaged in insurrection, or given aid or comfort to those who have, can be disqualified from running for office. There is an opposing candidate who is also filing suits to advocate for removing people from the ballot who may not agree with their policy.\n\nDr. Cornell West (independent), Robert F. Kennedy (independent), Donald Trump (Republican), and others are all potential targets of this egregious misuse of the 14th Amendment.\n\nWe cannot let this threat to our Republic continue. USJF will intervene in this effort through the Election Integrity Task Force by closely monitoring these states and plan to go to every one of these states, providing letter briefs to the top state election officials. We are also going to file Constitutional Law Briefs in the districts where there is court action on this.\n\nWe cannot let our Republic turn into a Banana Republic by creating an election where there is only one choice for people. We have to allow for discourse and differences of opinions to give our voters a say in who will lead them.\n\nReiteration of Call to Action:\nWe need your support to fight against this misuse of the 14th Amendment and protect the integrity of our elections. Sign the enclosed form and make a financial contribution today to ensure that we can continue our efforts. Your sponsorship is crucial in sustaining our fight for a fair and democratic electoral process.\n\nRemember, the power lies with the people, and together, we can make a difference. Join us in defending our Republic and preserving the rights of all candidates to run for office. We know we can count on you to stand with us in this critical battle.\n\nThank you for your unwavering support.\n\nSincerely,\n\n[Your Name]\n    Key Messages:\n\nDon\'t let them keep Donald Trump or other qualified candidates off the ballot.\n\nThe absurdity surrounding the misuse of the 14th Amendment is astounding. The 14th Amendment was added to the Constitution after the Civil War specifically to prevent members of the Confederacy from taking office. Now, they are trying to use it to keep any candidate radical interest groups don\'t want on the ballot, simply because they do not agree with those candidates\' viewpoints or policy ideas.\n\nSeveral organizations have already filed lawsuits in courts trying to keep Donald Trump off of the 2024 ballot using Article 14, Sec. 3, which is a disqualification clause written specifically after the Civil War. This clause states that no person who has already taken an oath of office to high offices such as congressional and presidential, who has engaged in insurrection, or given aid or comfort to those who have, can be disqualified from running for office. There is an opposing candidate who is also filing suits to advocate for removing people from the ballot who may not agree with their policy.\n\nDr. Cornell West (independent), Robert F. Kennedy (independent), Donald Trump (Republican), and others are all potential targets of this egregious misuse of the 14th Amendment.\n\nWe cannot let this threat to our Republic continue. USJF will intervene in this effort through the Election Integrity Task Force by closely monitoring these states and plan to go to every one of these states, providing letter briefs to the top state election officials. We are also going to file Constitutional Law Briefs in the districts where there is court action on this.\n\nWe cannot let our Republic turn into a Banana Republic by creating an election where there is only one choice for people. We have to allow for discourse and differences of opinions to give our voters a say in who will lead them.\n    Closing Statement:\n\nWe cannot let our Republic turn into a Banana Republic by creating an election where there is only one choice for people. We have to allow for discourse and differences of opinions to give our voters a say in who will lead them.\n\nThis threat to our Republic is urgent and cannot be ignored. We need your support to stand up against the misuse of the 14th Amendment and ensure that qualified candidates like Donald Trump, Dr. Cornell West, Robert F. Kennedy, and others are not unjustly removed from the ballot.\n\nJoin us in this fight to protect our democracy. Together, we can make a difference and preserve the principles that our nation was founded on. Your sponsorship is crucial in enabling us to intervene through the Election Integrity Task Force, monitor states, provide legal briefs, and advocate for fair and inclusive elections.\n\nWe know we can count on you to stand with us. Together, we can defend our Republic and ensure that every voice is heard. Thank you for your support and commitment to upholding the integrity of our elections.\n\nSincerely,\n\n[Your Name]\n    PS: Our Republic is under attack! The misuse of the 14th Amendment to remove qualified candidates from the ballot is a threat to our democracy. We cannot let radical interest groups dictate who can run for office based on their own personal agendas. \n\nAlready, lawsuits have been filed to keep Donald Trump, Dr. Cornell West, Robert F. Kennedy, and others off the 2024 ballot. This is an egregious misuse of the 14th Amendment, which was meant to prevent members of the Confederacy from taking office after the Civil War. \n\nWe cannot stand idly by while our Republic turns into a Banana Republic, with only one choice for the people. We must allow for discourse and differences of opinions to give our voters a say in who will lead them. \n\nJoin us in the fight to protect our democracy. Sign the form and make a donation to the USJF Election Integrity Task Force. Together, we can ensure that our Republic remains strong and that every voice is heard. \n\nI know we can count on you to stand up for our democracy. Don\'t let them keep Donald Trump or other qualified candidates off the ballot. Take action now!\n"""
    text = f"""What color is the sky?"""
    t0 = time.time()
    count = word_count(text)
    print(f"Time: {time.time() - t0}s")
    print(count)
    async def main():
        model_name = "gpt-4-0613"
        model_name = "gpt-4-32k"
        model_name = "gpt-3.5-turbo-1106"
        model_name = "gpt-4-vision-preview"
        model_name = "gpt-4-1106-preview"
        model_name = "gpt-4"
        model_name = "gpt-3.5-turbo"
        instructs_task = asyncio.create_task(TextCompletionEngine(model_name=model_name, temp=0.2, timeout=420).run_prompt(text, completions=2))
        output = await instructs_task
        cost = float(output["meta_data"]["cost_dollars"])
        # import code; code.interact(local=dict(globals(), **locals()))
        # for each completion, get the instructions for the article
        instruction = output["prompt"]
        return instruction, cost, output
    t0 = time.time()
    instruction, cost, output = asyncio.run(main())
    print(output)
    print(f"Instruction: {instruction}")
    print(f"Total cost: ${cost}")
    print(f"Total time: {time.time() - t0}s")
    # import code; code.interact(local=dict(globals(), **locals()))




