import uuid, os, re, tempfile, zipfile, aiohttp, asyncio, aiofiles, json, io, csv, logging, traceback, pickle, difflib, time, shutil, copy
from slack_bolt import App
from slack_sdk.errors import SlackApiError
from io import BytesIO, StringIO
import slack_block_generator as block_generator
from slack_sdk import WebClient
import openrouter_engine as ore
# import text_completion_engine as tce
# import subjectline_tools as slt


async def prompt_queue_monitor_message(client, core_response, text):
    await client.chat_update(channel=core_response.data['channel'], ts=core_response["ts"], text=f" ", 
                                                    blocks=[
    {
        "type": "section", 
        "text": {
            "type": "mrkdwn", 
            "text": f"{text}"
            }
    },
    {
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "Instruct Savant"
                },
                "action_id": "open_form"
            }
        ]
    },
    # {
    #     "type": "actions",
    #     "elements": [
    #         {
    #             "type": "button",
    #             "text": {
    #                 "type": "plain_text",
    #                 "text": "Stop Job"
    #             },
    #             "action_id": "open_promptfolder_form"
    #         }
    #     ]
    # }
    ])


def dict_to_yaml_str(d, yaml):
    # Recursively merge '<<:' keys into the parent dictionary
    def merge_duplicate_keys(d):
        if isinstance(d, dict):
            if '<<:' in d:
                d.update(d.pop('<<:'))
            return {k: merge_duplicate_keys(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [merge_duplicate_keys(v) for v in d]
        else:
            return d

    d = merge_duplicate_keys(d)
    output = StringIO()
    yaml.dump(d, output)
    return output.getvalue()

def split_text(text, max_length):
    chunks = []
    while len(text) > max_length:
        last_break = text[:max_length].rfind("\n")
        if last_break == -1:
            last_break = text[:max_length].rfind(" ")
        if last_break == -1:
            last_break = max_length
        chunks.append(text[:last_break])
        text = text[last_break:].lstrip()  # using lstrip() to remove any leading spaces or newlines
    chunks.append(text)
    return chunks

def insert_after(dict, target_key, insertion_dict):
    # create a list of the dict's keys
    keys = list(dict.keys())
    # find the index of the target key
    index = keys.index(target_key)
    # insert the new key after the target key
    keys.insert(index + 1, list(insertion_dict.keys())[0])
    # create a new dict with the new key order
    new_dict = {key: "blank" for key in keys}
    # fill the values of the new dict with the values of the old dict
    for key in keys:
        if key in dict:
            new_dict[key] = dict[key]
    # put the insertion dict in the new dict
    new_dict[list(insertion_dict.keys())[0]] = insertion_dict[list(insertion_dict.keys())[0]]
    return new_dict

async def get_thread_messages(body, client, logger):
    try:
        # Extracting the message text and channel details
        text = body["event"]["text"]
        channel_id = body["event"]["channel"]

        # If message is part of a thread, use thread_ts to get all messages in the same thread
        thread_ts = body["event"].get("thread_ts") or body["event"].get("ts")

        # Call conversations.replies method to get all messages in the thread
        response = await client.conversations_replies(
            channel=channel_id,
            ts=thread_ts
        )

        # Check if the call was successful
        if response["ok"]:
            # Get the list of messages in the thread
            messages = response["messages"]
            return messages

        else:
            raise Exception("Error retrieving thread messages: " + response["error"])

    except Exception as e:
        logger.exception(f"Error processing message: {e}\n\n{traceback.format_exc()}")

async def cycle_loading_reaction_emojis(job_id, job_info, channel_id, client, logger):
    emojis = ["hourglass", "hourglass_flowing_sand"]
    index = 0
    starting_rate = 0.5
    rate_limit_wait_time = 1 # time to wait before slowing down the rate
    slower_rate = 5
    if job_id in job_info:
        core_response_ts = job_info[job_id]['core_response_ts']
        if core_response_ts is not None:
            try:
                # Start by reacting with :red:
                await client.reactions_add(
                    channel=channel_id,
                    timestamp=core_response_ts,
                    name='red_circle',
                )
            except SlackApiError as e:
                logger.info(f"Error adding initial red emoji:")
    while not job_info.get(job_id, {}).get('completed', True):
        if index*starting_rate > rate_limit_wait_time:
            await asyncio.sleep(slower_rate)
        else:
            await asyncio.sleep(starting_rate)
        emoji = emojis[index % len(emojis)]
        if job_id in job_info:
            core_response_ts = job_info[job_id]['core_response_ts']
            if core_response_ts is not None:
                try:
                    # Remove previous reaction
                    if index > 0:
                        await client.reactions_remove(
                            channel=channel_id,
                            timestamp=core_response_ts,
                            name=emojis[(index - 1) % len(emojis)],
                        )
                    # Add new reaction
                    await client.reactions_add(
                        channel=channel_id,
                        timestamp=core_response_ts,
                        name=emoji,
                    )
                except SlackApiError as e:
                    logger.info(f"Error updating message with emoji: {e}")
        index += 1

    # Once the job is completed, replace :red: with :large_green_circle:
    if job_id in job_info:
        core_response_ts = job_info[job_id]['core_response_ts']
        if core_response_ts is not None:
            try:
                # Remove :red: reaction
                await client.reactions_remove(
                    channel=channel_id,
                    timestamp=core_response_ts,
                    name='red_circle',
                )
                # Add :large_green_circle: reaction
                # await client.reactions_add(
                #     channel=channel_id,
                #     timestamp=core_response_ts,
                #     name='large_green_circle',
                # )
                # Remove previous reaction
                await client.reactions_remove(
                    channel=channel_id,
                    timestamp=core_response_ts,
                    name=emojis[(index - 1) % len(emojis)],
                )
            except SlackApiError as e:
                logger.info(f"Error updating message with emoji:")

# async def gen_headlines_from_message(body, logger, client, thread_ts, slack_custom_actions_toolbox, engine, always_run=False):
    
#     # Extracting the message text and channel details
#     channel_id = body["event"]["channel"]
#     # get this bot's id
#     bot_id = slack_custom_actions_toolbox.bot_id
    
#     try:
#         # create a job id from the body message ts and the bot's id
#         job_id = f"{body['event']['ts']}_{bot_id}"
#         # job info is a dict 
#         job_info = {job_id: {"completed": False, "core_response_ts": body['event']['ts']}}
#         # # If message is part of a thread, use thread_ts to reply in the same thread
#         # thread_ts = body["event"].get("thread_ts") or body["event"].get("ts")
#         # import code; code.interact(local=dict(globals(), **locals()))
#         # Create a user mapping from user ID to user name
#         # user_mapping = {user_info['id']: user_info['real_name'] for names in s.slack_names for user_name, user_info in names.items()}

#         result_dict = {}
#         # Checking if the message starts with "subjectline" or "Subjectline"
#         if body["event"]["text"].replace(f"<@{bot_id}>", "").lstrip().lower().startswith("subjectline") or \
#                 always_run:

#             asyncio.create_task(cycle_loading_reaction_emojis(job_id, job_info, channel_id, client, logger))
#             thread_msgs = await get_thread_messages(body, client, logger)
#             for message in thread_msgs:
#                 # starting with the first message in the thread
#                 # 1. download and get the text content of all files in the msg. Add the text content to the result_dict
#                 # 2. add the main message text content to the result_dict
#                 text = message["text"]
#                 # filter out the bot's name from the text
#                 if text.startswith(f"<@{bot_id}>"):
#                     text = text[len(f"<@{bot_id}>"):]
#                     # remove the whitespace from just the start of the text
#                     text = text.lstrip()
#                     # remove "Subjectline" or "subjectline" and s ending varients from (only the start of) the text
#                     if text.startswith("subjectline"):
#                         text = text[len("subjectline"):]
#                     elif text.startswith("Subjectline"):
#                         text = text[len("Subjectline"):]
#                     elif text.startswith("subjectlines"):
#                         text = text[len("subjectlines"):]
#                     elif text.startswith("Subjectlines"):
#                         text = text[len("Subjectlines"):]

#                 if "files" in message:
#                     for file in message["files"]:
#                         file_id = file["id"]
#                         file_name = file["name"]
#                         file_type = file["filetype"]
#                         raw_text = ""
#                         if file_type == "text":
#                             file_contents = await download_file_content(file_id, os.environ["SLACK_TOKEN"])
#                             # if the file is a txt file, then add the contents to the text variable
#                             raw_text = "\n" + file_contents 
#                         elif file_type == "html":
#                             file_contents = await download_file_content(file_id, os.environ["SLACK_TOKEN"])
#                             # if the file is an html file, then convert it to a txt file and add the contents to the text variable
#                             from langchain.document_loaders import UnstructuredHTMLLoader
#                             # save the html file to a temporary directory
#                             with open(f"/tmp/{file_name}", "w") as f:
#                                 f.write(file_contents)
#                             loader = UnstructuredHTMLLoader(f"/tmp/{file_name}")
#                             doc = loader.load() 
#                             raw_text = "\n" + doc[0].page_content
#                             # delete the temporary file
#                             os.remove(f"/tmp/{file_name}")
#                         elif file_type == "zip":
#                             # TODO: unzip the entire folder and read throught each file
#                             raw_text = ""
#                         else:
#                             try:
#                                 file_contents = await download_file_content(file_id, os.environ["SLACK_TOKEN"])
#                                 # save the unknown file to a temporary directory
#                                 with open(f"/tmp/{file_name}", "w") as f:
#                                     f.write(file_contents)
#                                 from langchain.document_loaders import UnstructuredFileLoader
#                                 loader = UnstructuredFileLoader(f"/tmp/{file_name}")
#                                 doc = loader.load()
#                                 raw_text = "\n" + doc[0].page_content
#                                 # delete the temporary file
#                                 os.remove(f"/tmp/{file_name}")
#                             except:
#                                 # log the error, variable states and traceback
#                                 logger.exception(f"Error processing file: {file_name}\n\n{traceback.format_exc()}")
#                                 # just ignore the file
#                                 raw_text = ""
#                         print(raw_text)
#                         #print(tok_len(raw_text))
#                         ts = time.time()
#                         result_dict[ts] = {}
#                         result_dict[ts]['message'] = raw_text

#                 ts = time.time()
#                 result_dict[ts] = {}
#                 result_dict[ts]['message'] = text

#             max_response_len = 1500
#             model_name = "anthropic/claude-3-haiku"  # Set your model name
#             # # get the context for the subjectline generator
#             # reply_model = tce.TextCompletionEngine()
#             char_limit = 20000 - max_response_len
#             # import code; code.interact(local=dict(globals(), **locals()))
#             fitted_context = trim_content(result_dict, char_limit).strip()
#             # # clean up the context by removing the curly brackets and replacing them with square brackets
#             # fitted_context = fitted_context.replace("{", "[").replace("}", "]")
#             # # encode and decode the prompt to remove any special characters
#             # fitted_context = fitted_context.encode("ascii", "ignore").decode()
#             # print(fitted_context)
            
#             # # use the textcompletionengine to get instructions on how to write the subjectlines
#             # reply_model = tce.TextCompletionEngine(model_name=model_name, temp=0.05)

#             prompt = f"""You are a LLM chatbot named Savant, Copywriter whose mission is to assist users. Your ultimate objectives are to minimize suffering, enhance prosperity, and promote understanding.
# Below is a brainstorming chat thread between users and a subjectline creating bot. The bot is not very good at following instructions and needs your help to focus. You must be very clear when talking to it.
# Right now we need to concisely summarize the user's writing instructions for the bot.


# Chat Thread:
# {fitted_context}


# User Writing Instructions:
# """
#             creativity_boost = """Unleash your creativity and craft a masterpiece of originality that will leave an indelible mark on your readers. Dare to break free from the shackles of convention, forging a path illuminated by the power of your unique voice. Weave a tapestry of words that shimmers with vivid imagery, each thread a novel metaphor that invites the reader to see the world anew. Embrace the uncharted territories of language, fearlessly experimenting with unexpected combinations that spark the imagination and ignite the soul. Let every sentence be a revelation, a testament to your unwavering commitment to clarity and precision, yet alive with the boundless energy of innovation. Create a work that is not merely memorable, but unforgettable-a beacon of originality that will forever stand as a testament to the indomitable spirit of your creativity."""
#             # reply = await reply_model.run_prompt(prompt, completions=1)
#             # reply_text = reply['completions'][0]['response']
#             output = await engine.acomplete(prompt, completions=1, model=model_name, max_tokens=500, temp=0.05)
#             writing_instructions = creativity_boost + "\n" + output['completions'][0]
#             print(writing_instructions)


#             # st = slt.SubjectlineTools()
#             # reply = await st.generate_headlines_andor_subheads(fitted_context, n=10, 
#             #                                   min_score_threshold=3.3, max_attempts=1,
#             #                                   num_generations_per_openai_call=63, num_openai_calls=40,
#             #                                   list_elements_description="unique, engaging and concise subjectlines", 
#             #                                   one_word_description="subjectline", 
#             #                                   writing_instructions=reply_text,
#             #                                   head_len=60,
#             #                                   model_name=model_name, pr=True)
#             # preview_text = await st.generate_headlines_andor_subheads(fitted_context, n=10, max_attempts=1, min_score_threshold=3.3, 
#             #                                   num_generations_per_openai_call=63, num_openai_calls=40, 
#             #                                   list_elements_description="representative email preview text", 
#             #                                   one_word_description="preview text",
#             #                                   writing_instructions="",
#             #                                   model_name="anthropic/claude-3-haiku",
#             #                                   head_len=100, pr=True)
#             # run in parallel
#             reply_task = asyncio.create_task(st.generate_headlines_andor_subheads(fitted_context, n=10, max_attempts=1, min_score_threshold=3.3, 
#                                               num_generations_per_openai_call=63, num_openai_calls=50, 
#                                               list_elements_description="unique, engaging and direct subjectlines", 
#                                               one_word_description="subjectline", 
#                                               writing_instructions=writing_instructions,
#                                               head_len=60,
#                                               model_name="anthropic/claude-3-haiku:beta",
#                                               temperature=2, 
#                                               pr=True, banned_keywords=[]))
#             preview_task = asyncio.create_task(st.generate_headlines_andor_subheads(fitted_context, n=10, max_attempts=1, min_score_threshold=3.3, 
#                                               num_generations_per_openai_call=50, num_openai_calls=50, 
#                                               list_elements_description="representative email preview text", 
#                                               one_word_description="email preview text",
#                                               writing_instructions=writing_instructions,
#                                               model_name="anthropic/claude-3-haiku:beta",
#                                               temperature=2,
#                                               head_len=100, pr=True))
#             # wait for the tasks to complete
#             await asyncio.gather(reply_task, preview_task)
#             reply = reply_task.result()
#             preview_text = preview_task.result()

#             def ensure_10_headlines(headlines_):
#                 if not headlines_:
#                     raise ValueError("The headline list is empty: headlines={}".format(headlines_))
#                 headlines = copy.deepcopy(headlines_)
#                 # If less than 10, stack the list until we have 10
#                 while len(headlines) < 10:
#                     headlines.extend(headlines)
#                 # Sort the headlines by score in descending order
#                 sorted_headlines = sorted(headlines, key=lambda x: float(x['score']), reverse=True)
#                 # Ensure we have exactly 10 headlines
#                 return sorted_headlines[:10]

#             # Process preview_text['top_n']
#             preview_text['top_n'] = ensure_10_headlines(preview_text['top_n'])

#             # Process reply['top_n']
#             reply['top_n'] = ensure_10_headlines(reply['top_n'])

#             # both are dictionaries with a top_n key. Build the reply text
#             try:
#                 reply_text = ""
#                 for i in range(1, 11):
#                     reply_text += f"*{reply['top_n'][i-1]['headline']}*\n_{preview_text['top_n'][i-1]['headline']}_\nScores: ({reply['top_n'][i-1]['score']}, {preview_text['top_n'][i-1]['score']})\n\n\n"
#             except Exception as e:
#                 reply_text = f"Error: {e}"
#                 logger.exception(f"Error in gen_headlines_from_message\n")
#                 import code; code.interact(local=dict(globals(), **locals()))
#             print(reply_text)
#             # import code; code.interact(local=dict(globals(), **locals()))
#             await client.chat_postMessage(
#                 channel=channel_id,
#                 text=reply_text,
#                 thread_ts=thread_ts
#             )
#             job_info[job_id]['completed'] = True
#     except Exception as e:
#         job_info[job_id]['completed'] = True
#         logger.exception(f"Error in gen_headlines_from_message\n")

async def thread_bot_responder(body, client, app, channel_id, thread_ts, logger, redis_client, slack_custom_actions_toolbox, engine, cached_content=None):
    job_id = f"{body['event']['ts']}_{slack_custom_actions_toolbox.bot_id}"
    # job info is a dict 
    job_info = {job_id: {"completed": False, "core_response_ts": body['event']['ts']}}
    try:
        # Fetch all messages in the thread
        cursor = None
        all_messages = []
        while True:
            replies_response = await app.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                cursor=cursor
            )
            messages = replies_response['messages']
            all_messages.extend(messages)

            response_metadata = replies_response.get('response_metadata', {})
            cursor = response_metadata.get('next_cursor')

            if not cursor:
                break
        # if the first message in the thread is from the bot AND
        # the last message in the thread is to the bot, then let the bot respond
        # TODO: let savant respond to ANY message asked of it
        # # if (all_messages[0]['user'] == slack_custom_actions_toolbox.bot_id or \
        #     f"<@{slack_custom_actions_toolbox.bot_id}>" in all_messages[0]['message']) and \
        #     all_messages[-1]['message'].startswith(f"<@{slack_custom_actions_toolbox.bot_id}>"):
        
        asyncio.create_task(cycle_loading_reaction_emojis(job_id, job_info, channel_id, client, logger))
        # Now all_messages contains all the messages in the thread
        # Process the messages and download the files as needed
        file_contents = {}

        # Create a user mapping from user ID to user name
        user_mapping = {user_info['id']: user_info['real_name'] for names in slack_custom_actions_toolbox.slack_names for user_name, user_info in names.items()}
        bot_id = slack_custom_actions_toolbox.bot_id
        # Bot's real name (replace with actual bot's ID)
        bot_real_name = user_mapping.get(bot_id, 'BotName')
        # if their are at least 6 messages in the thread and the first message is from the bot
        # then this is a Savant Job. Therefore we know the message structure let the bot respond
        # basically just ignore the csv file and the templates folder
        if len(all_messages) >= 4 and all_messages[0]['user'] == bot_id:
            # import code; code.interact(local=dict(globals(), **locals()))   
            # Get the file ID from the 4th message (if the 4th message is a file)
            file_id_4th = all_messages[2]['files'][0]['id']
            file_contents["prompt"] = await download_file_content(file_id_4th, os.environ["SLACK_TOKEN"])

            # Get the file ID from the 5th message
            file_id_5th = all_messages[3]['files'][0]['id']
            file_contents["completion_1"] = await download_file_content(file_id_5th, os.environ["SLACK_TOKEN"])

            # Get the file IDs from subsequent all_messages and add them as completion_n
            completion_count = 2
            for message in all_messages[4:]:
                if 'files' in message and message['files'][0]['filetype'] == 'text':
                    file_id = message['files'][0]['id']
                    file_contents[f"completion_{completion_count}"] = await download_file_content(file_id, os.environ["SLACK_TOKEN"])
                    completion_count += 1
            file_contents["first_message_count"] = completion_count + 2

            # # Save the combined content in Redis, using the thread_ts as the key (remove the '.' from the thread_ts)
            # redis_key = f"thread_content_{thread_ts.replace('.', '')}"
            # redis_client.set(redis_key, json.dumps(file_contents))


            # show the LLM the job metrics
            metrics = all_messages[0]['blocks'][0]['text']['text']
            # import code; code.interact(local=dict(globals(), **locals()))
            # user map all the ids in the metrics to real names
            for user_id in user_mapping:
                if f"<@{user_id}>" in metrics:
                    metrics = metrics.replace(f"<@{user_id}>", f"Job settings for {user_mapping[user_id]}")
                    # remove everything after writing_instructions: (including writing_instructions:)
                    metrics = metrics.split("writing_instructions:")[0]
                    break

            # Initialize the result dictionary with prompt and completions
            result_dict = {
                "0": {"real_name": "Prompt", "message": file_contents["prompt"]},  
                "1": {"real_name": "Completion 1", "message": file_contents["completion_1"]}
            }

            # Add other completions if available TODO: make this dynamic instead of hardcoding 20
            for i in range(2, 100):  # Adjust the range based on the number of completions
                completion_key = f"completion_{i}"
                if completion_key in file_contents:
                    result_dict[f"{i}"] = {"real_name": f"Completion {i}", "message": file_contents[completion_key]}
            # find the largest key 
            largest_key = max([int(key) for key in result_dict.keys()])
            # Add the metrics
            result_dict[f"{largest_key+1}"] = {"real_name": "Metrics", "message": metrics}
        else:
            # we're just responding to a message thread so read it all in
            file_contents["first_message_count"] = 0
            result_dict = {}

        # Add the rest of the messages with real names
        for message in all_messages[file_contents["first_message_count"]:]:
            if 'files' in message and message['files'][0]['filetype'] == 'text':
                file_id = message['files'][0]['id']
                name_of_file = message['files'][0]['name']
                txt_file_contents = await download_file_content(file_id, os.environ["SLACK_TOKEN"])
                message['text'] = message['text'] + f'\n' + txt_file_contents
                message['text'] = message['text'].replace(f"<@{bot_id}>", "Savant")
            ts = message['ts']
            user_name = user_mapping.get(message['user'], "UserJohnDoe")
            result_dict[ts] = {"real_name": user_name, "message": message['text']}

        # from the first message get the model_name
        # text = all_messages[0]['text']
        # find the last \n and get all the text after that
        # try:
        #     text = all_messages[0]['blocks'][0]['text']['text']
        #     model_text_start = text[text.find('model: ')+7:]
        #     model_text_end = model_text_start[:model_text_start.find('\n')]
        #     model_name = model_text_end.strip()
        #     print(model_name)
        #     n = tce.TextCompletionEngine(model_name=model_name).context_len()  # Context window size in tokens

        # except Exception as e:
        #     print(e)
        #     # if there is an error for any reason then use the default model
        #     model_name = "gpt-4-0613"
        #     print(model_name)
        #     n = tce.TextCompletionEngine(model_name=model_name).context_len()  # Context window size in tokens
        # import code; code.interact(local=dict(globals(), **locals()))
        
        # (Note you have access to message embedded txt files and the ability to read and analyze the file contents)

        # # Usage example
        # p = 1500 + tok_len(system_message)  # Padding size in tokens
        char_limit = 180000
        combined_messages = trim_content(result_dict, char_limit)

        print(combined_messages)

        system_message = f"""You are a LLM chatbot named {bot_real_name} whose mission is to assist users. Your ultimate objectives are to minimize suffering, enhance prosperity, and promote understanding.

You can see the current chat thread below (we're using a scrolling context window, which cuts out older text if the chat thread can't fit in the window).

Interpreting chat context layout:
1. Prompt: A detailed prompt for a llm to write an email/newsletter
2. Completion(s): Email(s) generated by the llm (called completions)
3. Metrics: Metrics and general info about the job, LLM used, time taken, user who launched the job, etc.
4. General chat between users and yourself 

Current chat context:\n\n\n{combined_messages}\n\n\nNow, let's generate a helpful response to the user's latest message:"""

        # create a reply message
        # reply_model = tce.TextCompletionEngine(model_name=model_name, temp=0.05)
        # reply = await reply_model.run_prompt(system_message+combined_messages, completions=1)
        # reply_text = reply['completions'][0]['response']

        output = await engine.acomplete(system_message, completions=1, model="anthropic/claude-3.5-sonnet:beta", temp=0.05)
        reply_text = output['completions'][0]
        print(reply_text)


        await app.client.chat_postMessage(
            channel=channel_id,
            text=reply_text,
            thread_ts=thread_ts
        )
        # if the text in the first message of the thread starts with the bot id and then subjectline, then use the headline generator bot
        # elif all_messages[0]['text'].startswith(f"<@{slack_custom_actions_toolbox.bot_id}> subjectline") or \
        #     all_messages[0]['text'].startswith(f"<@{slack_custom_actions_toolbox.bot_id}> Subjectline"):

        #     print("gen_headlines_from_message")
        #     # Schedule gen_headlines_from_message to run on the event loop
        #     await gen_headlines_from_message(body, logger, client, thread_ts, slack_custom_actions_toolbox, always_run=True)
    except SlackApiError as e:
        # await stack_trace_message(app.client, user_id, replies_response.data['channel'], replies_response["ts"], e, logger)
        logger.exception(f"Error fetching thread replies:")
    job_info[job_id]['completed'] = True
    

# def tok_len(text, model_name="gpt-4"):
#     return int(tce.TextCompletionEngine(model_name=model_name).tok_len(text))

def construct_combined_message(result_dict, messages_only=False):
    combined_message_parts = []
    prev_user = None

    for ts, content in sorted(result_dict.items(), key=lambda x: float(x[0])):
        
        real_name = content.get('real_name', 'blank_name')
        message = content['message']
        part = '\n' + message if real_name == prev_user else '\n\n' + real_name + ':\n' + message

        combined_message_parts.append(part)
        prev_user = real_name

    combined_message = ''.join(combined_message_parts)
    return combined_message
            
def trim_content(result_dict, char_limit):
    trimmed_dict = result_dict.copy()
    combined_message = construct_combined_message(trimmed_dict)
    # append all the messages to get the total number of characters
    total_chars = sum([len(content['message']) for ts, content in trimmed_dict.items()])
    print(f"Total tokens: {total_chars}")
    while total_chars > char_limit:
        # Get the key for the first message in trimmed_dict
        first_key = sorted(trimmed_dict.keys())[0]
        first_message = trimmed_dict[first_key]['message']
        # Cut 200 tokens from the first message, or remove it if fewer than 200 tokens remain
        if len(first_message) > 200:
            new_message = first_message[200:len(first_message)]
            trimmed_dict[first_key]['message'] = new_message
        else:
            del trimmed_dict[first_key]
        # Reconstruct the combined message and recheck the token length
        combined_message = construct_combined_message(trimmed_dict)
        total_chars = sum([len(content['message']) for ts, content in trimmed_dict.items()])
        print(f"Total chars: {total_chars}")
    return combined_message

async def update_form(client, body, old_view, new_view, logger):
    logger.info(f'Updating form{body["view"]["id"]}')
    # if new_view['blocks'][2]['element']['initial_value'] and len(new_view['blocks'][2]['element']['initial_value']) > 3000:
    #     text_box_alert_msg = """Can only display the last 3000 characters\n"""
    #     new_view['blocks'][2]['element']['initial_value't_box_alert_msg + new_view['blocks'][2]['element']['initial_value'][-(3000-int(len(text_box_alert_msg))):]
    # import code; code.interact(local=dict(globals(), **locals())] =  tex)
    # update the modal form
    try:
        response = await client.views_update(
                view_id=body["view"]["id"],
                hash=body["view"]["hash"],
                view=new_view
            )
        return response
    except SlackApiError as e:
        logger.exception(f"Error updating form: {e}\n\n{traceback.format_exc()}\n\n\nold_view\n{old_view}\n\n\nnew_view\n{new_view}")
        # if the error is 
        """>>> e.response.data['error']
'invalid_arguments'"""
        # close the modal and send the error message
        try:
            await client.views_update(
                view_id=body["view"]["id"],
                hash=body["view"]["hash"],
                view={
                    "type": "modal",
                    "title": {
                        "type": "plain_text",
                        "text": "Form Version out of sync"
                    },
                    # "submit": {
                    #     "type": "plain_text",
                    #     "text": "Submit"
                    # },
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "plain_text",
                                "text": "Form Version out of sync. Close form and try again."
                            }
                        }
                    ]
                }
            )
        except SlackApiError as eh:
            logger.exception(f"Error closing modal: {eh}")
        print(e)
        # import code; code.interact(local=dict(globals(), **locals()))


async def send_form(client, body, view, logger):
    # Log the trigger_id
    logger.info(body['trigger_id'])
    # if writing instructions is longer than 3000 characters (the max for a slack message) then keep the last 3000 characters
    # if view['blocks'][2]['element']['initial_value'] and len(view['blocks'][2]['element']['initial_value']) > 3000:
    #     text_box_alert_msg = """Can only display the last 3000 characters\n"""
    #     view['blocks'][2]['element']['initial_value'] =  text_box_alert_msg + view['blocks'][2]['element']['initial_value'][-(3000-int(len(text_box_alert_msg))):]
    # import code; code.interact(local=dict(globals(), **locals()))
    # Open the modal form
    response = await client.views_open(
        trigger_id=body["trigger_id"],
        view=view
    )

def ensure_view_size(view):
    """
    Ensure that all initial_value fields in the view's blocks are less than 3000 characters.
    If the initial_value in block at index 2 exceeds this limit, truncate it and append an alert message.
    """
    # Iterate through blocks and check initial_value lengths
    for idx, block in enumerate(view['blocks']):
        text_box_alert_msg = """Can only display the last 3000 characters\n""" if idx == 2 else ""
        
        if 'element' in block and 'initial_value' in block['element'] and len(block.get('element', {'initial_value': []}).get('initial_value', [])) > 3000:
            block['element']['initial_value'] = text_box_alert_msg + block['element']['initial_value'][-(3000-int(len(text_box_alert_msg))):]

    return view

# class ViewTooLargeError(Exception):
#     pass

# from slack_sdk.errors import SlackApiError

# async def attempt_send_view(client, body, view):
#     try:
#         response = await client.views_open(
#             trigger_id=body["trigger_id"],
#             view=view
#         )
#         return response
    
#     except SlackApiError as e:
#         if 'view_too_large' in str(e.response):
#             raise ViewTooLargeError("The view is too large.")
#         else:
#             raise e 

# async def send_form(client, body, view, logger):
#     # Log the trigger_id
#     logger.info(body['trigger_id'])
#     # Try to open the modal form
#     response = None
#     try:
#         response = await attempt_send_view(client, body, view)
#         return response

#     except Exception as e:
#         print(e)
#         # traceback.print_exc()
#         print(traceback.print_exc())
#         print(response)
#         import code; code.interact(local=dict(globals(), **locals()))
#         # If there is a "view_too_large" error, start the search from the end
#         last_search_position = len(view['blocks']) - 1
#         while last_search_position >= 0:
#             block = view['blocks'][last_search_position]
#             if 'element' in block and 'initial_value' in block['element'] and len(block['element']['initial_value']) > 3000:
#                 # Truncate the initial_value and retry
#                 if last_search_position == 2:
#                     text_box_alert_msg = """Can only display the last 3000 characters\n"""
#                 else:
#                     text_box_alert_msg = ""
#                 block['element']['initial_value'] =  text_box_alert_msg + block['element']['initial_value'][-(3000-int(len(text_box_alert_msg))):]
#                 try:
#                     response = await attempt_send_view(client, body, view)
#                     return response
#                 except ViewTooLargeError:
#                     last_search_position -= 1
#                     continue
#             last_search_position -= 1
#         # If no excessively long initial_values are found, raise the error
#         raise Exception("View is too large even after truncating initial_values.")


async def build_form(user_init_values, temp_dir, default_template_path, edit_form=False, debug=False, model_options=None):

    # Generate the form blocks with the user's init_values
    blocks = block_generator.SlackBlockGenerator(temp_dir, default_template_path, user_init_values).generate_slack_blocks(debug=debug, model_options=model_options)
    modal_header = {
"type": "modal",
"callback_id": "copy_generator_modal_form",
"title": {
    "type": "plain_text",
    "text": "Savant, Copywriter"
},
    "submit": {
    "type": "plain_text",
    "text": "Send to Savant"
},
}
    view = modal_header.copy()
    if edit_form:
        view["callback_id"] = "copy_generator_modal_form_edit"
    view["blocks"] = blocks["blocks"]
    return view

async def build_form_v2(user_init_values, edit_form=False, debug=False, model_options=None):

    # Generate the form blocks with the user's init_values
    blocks = block_generator.SlackBlockGeneratorV2(user_init_values).generate_slack_blocks(debug=debug, model_options=model_options)
    modal_header = {
"type": "modal",
"callback_id": "copy_generator_modal_form",
"title": {
    "type": "plain_text",
    "text": "Savant, Copywriter"
},
    "submit": {
    "type": "plain_text",
    "text": "Send to Savant"
},
}
    view = modal_header.copy()
    if edit_form:
        view["callback_id"] = "copy_generator_modal_form_edit"
    view["blocks"] = blocks["blocks"]
    return view

async def get_user_init_values(user_id, global_init_values, redis_client, first_pass):
    # Get the user's init_values from Redis
    user_init_values_json = redis_client.get(f"{user_id}_job_form")

    # If user_init_values_json is not None, load the user's init_values
    if (user_init_values_json and not first_pass):
        user_init_values = json.loads(user_init_values_json)
        # If the user's init_values are not of the same type or length as the base init_values, use the base init_values
        # (user_init_values == global_init_values)
        # if (type(user_init_values) != type(global_init_values) or len(user_init_values) != len(global_init_values)):
        #     user_init_values = global_init_values
    else:
        user_init_values = global_init_values
    # if the user's init_values template, folder_1, folder_2 values are not a valid path in the templates folder, find any valid path
    try:
        if not os.path.exists(build_new_default_template_path(user_init_values)):
            print("path suggested in user_init_values is not valid. setting all to None. Valid templates should build themselves and the user should be able to select one later.")
            for other_key in ["template", "folder_1", "folder_2"]:
                user_init_values[other_key]["value"] = "None"
    except:
        # set the user's init_values to the global init_values and set their folder values to the defaults
        user_init_values = global_init_values
        for other_key in ["template", "folder_1", "folder_2"]:
            user_init_values[other_key]["value"] = "None"

    # save the user's init_values to Redis
    redis_client.set(f"{user_id}_job_form", json.dumps(user_init_values))
    return user_init_values

def build_new_default_template_path(dict_init_values):
    new_default_path = "templates/"
    # go through templates, folder_1, folder_2 and add to new_default_path if not "None"
    for key in ["template", "folder_1", "folder_2"]:
        if dict_init_values[key]["value"] != "None":
            new_default_path += dict_init_values[key]["value"] + "/"
    return new_default_path

async def save_promptfolder_to_redis(client, channel_id, file_id, file_name, user_id, redis_client, token, logger):
    if "templates" in file_name and file_name.endswith(".zip"):
        unzipped_folder = await download_and_unzip_folder(file_id, token)
        # add any future folder validation checks here
        try:
            first_txt_filename = list(unzipped_folder.keys())[0].split('.')[0]
        except:
            error_msg = f"first_txt_filename is not valid. Folder name({file_name[:-4]}) MUST have an identically titled .txt file({first_txt_filename}) to hold the folder's core prompt"
            await client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text=error_msg
            )
            raise Exception(error_msg)
        pickled_unzipped_folder = pickle.dumps(unzipped_folder)
        # validate that the first file in the folder is named the same as the folder

        redis_key = f"{user_id}_prompts_folder"
        redis_client.set(redis_key, pickled_unzipped_folder)

        logger.info(f"File {file_name} with ID {file_id} has been downloaded, unzipped, and stored in Redis as a serialized folder for user {user_id}")

        response = await client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text=f"New templates folder {file_name} successfully uploaded and set up for <@{user_id}>. Overwriting your previous Templates. To reset your templates, upload a new templates folder or press the Save Templates button."
        )
    else:
        await client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text=f"File {file_name} with ID {file_id} is not a templates.zip folder. Please upload a .zip folder that has \"templates\" in it\'s name."
        )
    return response

def get_template_selections(view, init_values, folder_path, button_states):
    if view:
        submitted_data = view["state"]["values"]
        # Convert the submitted_data to init_values
        init_values = form2init_values_list(submitted_data, init_values, folder_path, button_states)
    # get the first len(init_values) - 4 elements of init_values
    template_selections = []
    for idx, key in enumerate(["template", "folder_1", "folder_2"]):
        if init_values[key]["visable"] and init_values[key]["value"] != "None":
            template_selections.append(str(init_values[key]["value"]))

    def get_end_folder(*paths):
        def get_last_folder(path):
            return path.strip().split("/")[-1]
        last_folders = [get_last_folder(path) for path in paths]
        return tuple(last_folders)
    template_selections = get_end_folder(*template_selections)
    return list(template_selections)

async def stack_trace_message(client, user_id, channel, ts, e, logger):
    stack_trace = traceback.format_exc()
    logger.exception(f"Error generating articles for {user_id}: {e}")
    await client.chat_postMessage(
        channel=channel,  # core_response.data['channel'],
        thread_ts=ts,  # core_response["ts"],
        text=f"Error: {e}\n\n\nSTACKTRACE\n\n{stack_trace}",
        blocks=[]
    )

async def job_started_message(client, user_id, monitor_channels, init_values, logger):
    core_response = await client.chat_postMessage(
        channel=monitor_channels[0],
        # use a red emoji to make it stand out
        text=f"<@{user_id}>\n:red_circle: :hourglass_flowing_sand: Job started\n{init_values['model']['value']}",
        blocks=[]
    )
    # Set the job_id (you can use any unique identifier for the job)
    job_id = f"{user_id}_{time.time()}"

    # Save the core_response_ts and original_message in job_info dictionary
    job_id_metadata = {
        'core_response_ts': core_response['ts'],
        'original_message': core_response['message']['text'],
        'completed': False,
    }
    return core_response, job_id, job_id_metadata

async def post_article(client, core_response, article, stats):
    return await client.chat_postMessage(channel=core_response.data['channel'], text=f"{article[:3000]}", 
                                              thread_ts=core_response["ts"], blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": article
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": stats
                },
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Natural Language Editor"
                    },
                    "action_id": "edit_piece",
                    "value": "edit_piece"
                }
            }
        ]
    )

# async def post_yaml_promptqueue

async def post_article_txt(client, core_response, article, stats, logger, temp_directory="/tmp", file_name=".txt"):
    # send the variable filled prompt as a .txt file
    if file_name == ".txt":
        unique_id = str(uuid.uuid4())
        file_name = f"{unique_id}.txt"
    prompt_file = os.path.join(temp_directory, file_name)
    with open(prompt_file, 'w') as file:
        file.write(article)
    # Send the prompt.txt file
    try:
        # with open(prompt_file, "rb") as file:
        #     response = await client.files_upload(
        #         channels=core_response.data['channel'],
        #         initial_comment=f"{stats}",
        #         file=prompt_file,
        #         thread_ts=core_response["ts"],
        #         title=file_name, 
        #     )
        # with open(prompt_file, "rb") as file:
        #     response = await client.files_upload(
        #         channels=core_response.data['channel'],
        #         initial_comment=f"",
        #         file=prompt_file,
        #         thread_ts=core_response["ts"],
        #         title=file_name, 
        #     )
        with open(prompt_file, "rb") as file:
            response = await client.files_upload_v2(
                file_uploads=[
                    {
                        "file": prompt_file,
                        "title": file_name,
                        "initial_comment": f"{stats}",
                        # "title": "New company logo",
                        # "content": f'{article}',
                        # "filename": "team-meeting-minutes-2022-03-01.md",
                    },
                    # {
                    #     "file": prompt_file,
                    #     "title": file_name,
                    #     "content": f'{article}',
                    # },
                ],
                channel=core_response.data['channel'],
                thread_ts=core_response["ts"],
                initial_comment=f"{stats}",
            )
    #     await client.chat_postMessage(channel=core_response.data['channel'], text=f" ", 
    #                                           thread_ts=core_response["ts"], blocks=[
    #         {
    #             "type": "section",
    #             "text": {
    #                 "type": "mrkdwn",
    #                 "text": stats
    #             }
    #         },
    #         # {
    #         #     "type": "section",
    #         #     "text": {
    #         #         "type": "mrkdwn",
    #         #         "text": stats
    #         #     },
    #         #     "accessory": {
    #         #         "type": "button",
    #         #         "text": {
    #         #             "type": "plain_text",
    #         #             "text": "Edit Piece"
    #         #         },
    #         #         "action_id": "edit_piece",
    #         #         "value": "edit_piece"
    #         #     }
    #         # }
    #     ]
    # )
        logger.info(f"Sent prompt file '{prompt_file}' to {core_response.data['channel']}")
    except SlackApiError as e:
        logger.exception(f"Error sending prompt file '{prompt_file}' to {core_response.data['channel']}:")
    # Remove the .txt file
    os.remove(prompt_file)

async def job_end_message(client, user_id, core_response, init_values, metadata):
    # drop prompt_template_selections from metadata
    metadata.pop("prompt_template_selections", None)
    # rename sf_template_name_id to job_name
    # metadata["sf_job_name"] = metadata.pop("sf_template_name_id", None)
    # pop the writing_instructions
    writing_instructions = str(metadata.pop("writing_instructions", ""))
    prompt_ = str(metadata.pop("prompt", ""))
    # if there are more than 200 characters in the writing_instructions then just send the first 200 + ...
    if writing_instructions and len(writing_instructions) > 200:
        writing_instructions = writing_instructions[:200] + "..."
        # if there are more than 5 \n characters in the writing_instructions then just send the first 5 + ...
        if writing_instructions.count("\n") > 4:
            writing_instructions = "\n".join(writing_instructions.split("\n")[:4]) + "..."
    metadata_text = "\n".join([f"{key}: {value}" for key, value in metadata.items()])
    response = await client.chat_update(channel=core_response.data['channel'], ts=core_response["ts"], text=f"<@{user_id}>\n", 
                                                    blocks=[
    {
        "type": "section", 
        "text": {
            "type": "mrkdwn", 
            "text": f"<@{user_id}>\n:large_green_circle: Job finished\nmodel: {init_values['model']['value']}\njob_name: {init_values['sf_template_name_id']['value']}\n{metadata_text}\nprompt:```{writing_instructions}```"
            }
    },
    {
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "Instruct Savant"
                },
                "action_id": "open_form"
            }
        ]
    },
    # {
    #     "type": "actions",
    #     "elements": [
    #         {
    #             "type": "button",
    #             "text": {
    #                 "type": "plain_text",
    #                 "text": "Quickedit your Promptfolder"
    #             },
    #             "action_id": "open_promptfolder_form"
    #         }
    #     ]
    # }
    ])

async def filled_prompt_to_file(client, prompt, core_response, metadata, logger, temp_directory="/tmp", file_name="prompt.txt", initial_comment=None):
    # send the variable filled prompt as a .txt file
    prompt_file = os.path.join(temp_directory, file_name)
    with open(prompt_file, 'w') as file:
        file.write(prompt)
    if initial_comment:
        initial_comment = f"{initial_comment}"
    else:
        initial_comment = f"Here is the prompt used for generation\nprompt_token_len: {metadata['tokens_prompt']}"
    # Send the prompt.txt file
    try:
        with open(prompt_file, "rb") as file:
            response = await client.files_upload_v2(
                channels=core_response.data['channel'],
                initial_comment=initial_comment,
                file=prompt_file,
                thread_ts=core_response["ts"],
                title=file_name, 
            )
        logger.info(f"Sent prompt file '{prompt_file}' to {core_response.data['channel']}")
    except SlackApiError as e:
        logger.exception(f"Error sending prompt file '{prompt_file}' to {core_response.data['channel']}:")
    # import code; code.interact(local=dict(globals(), **locals()))
    # Remove the prompt.txt file
    # os.remove(prompt_file)

async def string_to_slack(client, prompt, core_response, logger, initial_comment="", temp_directory="/tmp", file_name="prompt.txt"):
    # send the variable filled prompt as a .txt file
    prompt_file = os.path.join(temp_directory, file_name)
    with open(prompt_file, 'w') as file:
        # make sure the prompt is ascii safe
        prompt = prompt.encode('ascii', 'ignore').decode('ascii')
        file.write(prompt)
    # Send the prompt.txt file
    try:
        if file_name:
            with open(prompt_file, "rb") as file:
                response = await client.files_upload_v2(
                    channels=core_response.data['channel'],
                    initial_comment=initial_comment,
                    file=prompt_file,
                    thread_ts=core_response["ts"],
                    title=file_name, 
                )
        else:
            # just send a message
            response = await client.chat_postMessage(
                    channel=core_response.data['channel'],
                    text=prompt,
                    thread_ts=core_response["ts"],
                )
        logger.info(f"Sent file '{prompt_file}' to {core_response.data['channel']}")
        await asyncio.sleep(0.1)
        return response
    except SlackApiError as e:
        logger.exception(f"Error {e} while sending prompt file '{prompt_file}' to {core_response.data['channel']}:")

# async def edit_slack_message(client, core_response, new_text, logger):
#     try:
#         response = await client.chat_update(
#             channel=core_response.data['channel'],
#             ts=core_response["ts"],
#             text=new_text,
#             blocks=[]
#         )
#         return response
#     except SlackApiError as e:
#         logger.exception(f"Error editing slack message:")
#         return None

async def file_to_string(client, ts, channel, file_id, logger, temp_directory="/tmp", file_name="prompt.txt"):
    # send the variable filled prompt as a .txt file
    prompt_file = os.path.join(temp_directory, file_name)
    try:
        await download_file(file_id, temp_directory, os.environ["SLACK_TOKEN"])
        with open(prompt_file, 'r') as file:
            prompt = file.read()
        return prompt
    except SlackApiError as e:
        logger.exception(f"Error downloading file '{prompt_file}' from {channel}:")

async def send_button(client, core_response, text, button_text, action_id, logger):
    try:
        # Add a button to set the uploaded file as the Promptfolder
        # the text before the button should be the prompt
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": text
                },
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": button_text
                    },
                    "action_id": action_id
                }
            }
        ]
        
        response = await client.chat_postMessage(
            channel=core_response.data['channel'],
            thread_ts=core_response["ts"],
            blocks=blocks
        )
        return response
    except SlackApiError as e:
        logger.exception(f"Error sending button:")

async def send_prompt_folder(client, temp_dir, user_id, channel, ts, logger, init_cmt="\'s Templates",
                              msg="Would you like to set this folder as your main Templates?"):
    # send the prompts folder to the user
    copy_prompts_zipped = zip_folder(temp_dir)
    try:
        with open(copy_prompts_zipped, "rb") as file:
            response = await client.files_upload_v2(
                channels=channel,
                initial_comment=f"<@{user_id}>{init_cmt}",
                thread_ts=ts,
                file=copy_prompts_zipped,
                title=copy_prompts_zipped.split("/")[-1], 
            )
        logger.info(f"Sent copy prompt file '{copy_prompts_zipped}' to {channel}")

        await set_promptfolder_button(client, channel, ts, msg=msg) 
        
    except SlackApiError as e:
        logger.exception(f"Error sending copy prompt file '{copy_prompts_zipped}' to {channel}:")
    
    # delete the zip file
    os.remove(copy_prompts_zipped)
    return response

async def set_promptfolder_button(client, channel, ts, msg="Would you like to set this folder as your main Templates?"):
    # Add a button to set the uploaded file as the Promptfolder
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": msg
            },
            "accessory": {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "Save Templates"
                },
                "action_id": "set_promptfolder"
            }
        }
    ]
    
    response = await client.chat_postMessage(
        channel=channel,
        thread_ts=ts,
        blocks=blocks
    )
    return response

async def send_csv_articles(client, articles, user_id, core_response, logger):
    # Send the articles (each a string) to the user all in one csv file
    csv_file = await generate_csv_file(articles)
    try:
        with open(csv_file, "rb") as file:
            response = await client.files_upload_v2(
                channels=core_response.data['channel'],
                initial_comment="",
                file=csv_file,
                thread_ts=core_response["ts"],
                title=csv_file.split("/")[-1], 
            )
        logger.info(f"Sent articles file '{csv_file}' to {user_id}")
    except SlackApiError as e:
        logger.exception(f"Error sending articles file '{csv_file}' to {user_id}:")
    # delete the csv file
    os.remove(csv_file)

async def validate_init_values(client, init_values, user_id, monitor_channels, logger):
    try:
        temperature = float(init_values["temperature"]["value"])
        if temperature < 0 or temperature > 2:
            raise ValueError
    except ValueError:
        await client.chat_postEphemeral(
            channel=monitor_channels[0],
            user=user_id,
            text="Temperature must be a float between 0.0 and 2. Experiment with different values to see what works best for you."
        )
        return False, temperature, init_values[-1]
    
    try:
        completions = int(init_values["samples"]["value"])
        if completions < 1 or completions > 100:
            raise ValueError
    except ValueError:
        await client.chat_postEphemeral(
            channel=monitor_channels[0],
            user=user_id,
            text="Completions must be a whole integer between 1 and 100. Let the dev's know if you need more than 100 completions."
        )
        return False, temperature, completions
    if temperature == 0.0:
        # await client.chat_postEphemeral(
        #     channel=monitor_channels[0],
        #     user=user_id,
        #     text="Temperature of 0.0 defines a deterministic output (a given prompt will always respond with the same output). Deterministic output is useful when searching for the reliable prompt text. Will automatically set completions to 1 b/c all completions will be identical anyways."
        # )
        completions = 1
    return True, temperature, completions

old = '~'
new = '*'
def diff_emails(original, edited):
    original = original.splitlines()
    edited = edited.splitlines()
    d = difflib.Differ()
    diff = d.compare(original, edited)
    result = []
    for line in diff:
        if line.startswith('- '):
            result.append(old + line[2:] + old)  # wrap with '~' if removed
        elif line.startswith('+ '):
            result.append(new + line[2:] + new)  # wrap with '*' if added
        elif line.startswith('  '):  # if no change, add without prefix
            result.append(line[2:])
        # ignore '? ' lines as per requirement
    return '\n'.join(result)

def get_edited_email(diff_string):
    lines = diff_string.split('\n')
    edited = []
    for line in lines:
        if line.startswith(old) and line.endswith(old):  # lines removed from original
            continue
        elif line.startswith(new) and line.endswith(new):  # lines added in edited version
            edited.append(line[1:-1])
        else:  # lines present in both versions
            edited.append(line)
    return '\n'.join(edited)  # join lines with newline characters

# extract the user_prompts_folder from redis
def get_user_prompts_folder(user_id, redis_client, default_folder_path, logger, inits_on_first_start, pr=False):
    
    # print("inits_on_first_start", inits_on_first_start)
    # print("default_folder_path", default_folder_path)
    # Get the user's copy prompts from Redis
    redis_key = f"{user_id}_prompts_folder"
    # folder name is the last segment of default_folder_path
    folder_name = os.path.basename(default_folder_path)
    # redis_client.delete(redis_key)
    pickled_unzipped_folder = redis_client.get(redis_key)
    # print("pickled_unzipped_folder", pickled_unzipped_folder)
    # check that pickled_unzipped_folder is a path that exists
    if pickled_unzipped_folder and not inits_on_first_start:
        unzipped_folder = pickle.loads(pickled_unzipped_folder)

        # Call the function and get the path
        temp_dir = save_to_temp_folder(unzipped_folder, folder_name)
        # logger.info(f"Contents of {temp_dir}: {os.listdir(temp_dir)}")
        # import code; code.interact(local=dict(globals(), **locals()))
        if pr: print_directory_tree(temp_dir)
        return temp_dir
    else:
        logger.warning(f"Couldn't find the user's prompts folder in Redis: {redis_key}. Using default folder instead.")
        # Transform the default folder into a dictionary
        default_folder_dict = folder_to_dict(default_folder_path)
        # Save the default_folder_dict to a temporary directory
        temp_dir = save_to_temp_folder(default_folder_dict, folder_name)
        # # set redis key to something blank
        redis_client.set(redis_key, pickle.dumps(default_folder_dict))
        return temp_dir
    
# def folder_to_dict(folder_path):
#     folder_dict = {}
#     for root, dirs, files in os.walk(folder_path):
#         for file in files:
#             path = os.path.join(root, file)
#             relative_path = os.path.relpath(path, folder_path)
#             with open(path, 'rb') as f:
#                 content = f.read()
#             folder_dict[relative_path] = content
#     return folder_dict

def folder_to_dict(folder_path):
    folder_dict = {}
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith('.txt'): # Consider only .txt files
                path = os.path.join(root, file)
                relative_path = os.path.relpath(path, folder_path)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                folder_dict[relative_path] = content
    return folder_dict

# async save this unzipped_folder to a temp folder. We'll delete it later 
def save_to_temp_folder(unzipped_folder, folder_name):
    # unzipped_folder is a dictionary with the file path as the key and the file contents as the value
    # Create a temporary directory
    temp_dir = tempfile.mkdtemp()
    # Iterate over the files in the unzipped folder
    for file_path, content in unzipped_folder.items():
        # Skip any macOS-specific files or directories
        if '.DS_Store' not in file_path and '__MACOSX' not in file_path:
            # Create the full path for the new file
            full_path = os.path.join(temp_dir, file_path)
            # Make sure the directory for the new file exists
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            # Write the content to the new file
            with open(full_path, 'w') as f:
                f.write(content)
    # find the file and name the folder after it
    # the old line: first_txt_file = [f for f in os.listdir(temp_dir) if f.endswith('.txt')][0][:-4]
    first_txt_file = ""
    for f in os.listdir(temp_dir):
        if f.endswith('.txt'):
            first_txt_file = f[:-4]
            break

    new_temp_dir = tempfile.mkdtemp()
    destination_dir = os.path.join(new_temp_dir, first_txt_file)
    shutil.move(temp_dir, destination_dir)
    # replacing the folder name at the end of the destination_dir
    # the last segment of destination_dir is a random string. Rename just the last segment to the folder name
    new_path_name = os.path.join(os.path.dirname(destination_dir), folder_name)
    old_path_name = destination_dir + "/" + os.listdir(destination_dir)[0]
    os.rename(old_path_name, new_path_name) 
    return new_path_name

def print_directory_tree(directory):
    for root, dirs, files in os.walk(directory):
        level = root.replace(directory, '').count(os.sep)
        indent = ' ' * 4 * (level)
        print('{}{}/'.format(indent, os.path.basename(root)))
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            print('{}{}'.format(subindent, f))

def get_convo_id(channel_name, pr=False):
        # THIS IS A SKETCHY METHOD THAT IS NOT GUARANTEED TO WORK EVERY TIME
        conversation_id = None
        try:
            # print(app.client.conversations_list())
            # Call the conversations.list method using the WebClient
            application = App(token=os.environ["SLACK_TOKEN"])
            convo_list = application.client.conversations_list(limit=1000, types="public_channel, private_channel", exclude_archived=True)
            # for result in convo_list.data:
            #     # stoppage condition
            #     if conversation_id is not None:
            #         break
            #     # import code
            for channel in convo_list.data["channels"]:
                if pr: print(channel["name"])
                if channel["name"] == channel_name:
                    conversation_id = channel["id"]
                    # Print result
                    if pr: print(f"Found conversation ID: {conversation_id}")
                    break
            if conversation_id is None:
                # get the stack trace
                raise Exception(f"get_convo_id Channel {channel_name} not found.")
        except SlackApiError as e:
            print(f"Error: {e}")
        return conversation_id

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # File handler
    file_handler = logging.FileHandler("async_server.log", mode="a")
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)

    # Stream handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(log_formatter)
    logger.addHandler(stream_handler)

    return logger

async def download_file(file_id, token):
    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"https://slack.com/api/files.info?file={file_id}") as response:
            file_info = await response.json()
            file_url = file_info["file"]["url_private"]
            async with session.get(file_url) as file_response:
                file_content = await file_response.read()
    return file_content

async def download_and_unzip_folder(file_id, token):
    # Note: This code assumes that the names of files are unique across the entire directory structure. If there are files with the same name in different directories, their content will be overwritten in the unzipped_files dictionary.
    # Download the file
    file_content = await download_file(file_id, token)
    # Unzip the file content
    with tempfile.TemporaryDirectory() as temp_dir:
        with tempfile.NamedTemporaryFile() as temp_zip:
            temp_zip.write(file_content)
            temp_zip.seek(0)
            with zipfile.ZipFile(temp_zip.name, 'r') as archive:
                archive.extractall(temp_dir)

        # Read and store the unzipped files
        unzipped_files = {}
        for root, _, files in os.walk(temp_dir):
            for file in files:
                file_path = os.path.join(root, file)
                with open(file_path, 'rb') as f:
                    content = f.read().decode('utf-8', 'ignore')
                # Get the relative path from the temp directory to the file
                relative_path = os.path.relpath(file_path, temp_dir)
                unzipped_files[relative_path] = content
    return unzipped_files

async def download_file_content(file_id, token):
    # Construct the URL to download the file using Slack's files.info endpoint
    url = f"https://slack.com/api/files.info?file={file_id}"
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                raise Exception(f"Failed to download file info: {response.status}")
            file_info = await response.json()

    # Get the file download URL
    download_url = file_info['file']['url_private_download']

    # Download the file content
    async with aiohttp.ClientSession() as session:
        async with session.get(download_url, headers=headers) as response:
            if response.status != 200:
                raise Exception(f"Failed to download file: {response.status}")
            file_content = await response.read()

    return file_content.decode('utf-8', errors='ignore')

async def get_file_info(file_id, token):
    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"https://slack.com/api/files.info?file={file_id}") as response:
            file_info = await response.json()
    return file_info


def form2init_values_list(submitted_data, dict_init_values_, folder_path, button_states, action_taken=None):
    print(submitted_data)
    # submitted_data is data from a slack form submission
    # dict_init_values_ are the default values for the form
    # use a deepcopy on the dict_init_values_ to avoid changing the original
    dict_init_values = copy.deepcopy(dict_init_values_)
    template_path = os.path.join(folder_path, dict_init_values["template"]["value"])
    variables_path = os.path.join(folder_path, dict_init_values["template"]["value"], "vars")
    if not os.path.exists(template_path):
        # set everything to None if the template doesn't exist
        for key in ["template", "variables", "folder_1", "folder_2"]:
            dict_init_values[key]["value"] = "None"
    # check for path existence
    if not os.path.exists(variables_path) and os.path.exists(template_path):
        # if the path doesn't exist, then add a vars directory
        os.makedirs(variables_path)
    # set variables to "None" if there are no files in the directory
    if dict_init_values["template"]["value"] != "None" and len(os.listdir(variables_path)) == 0:
        dict_init_values["variables"]["value"] = "None"
    init_keys = []
    # routing submitted data to old dict_init_values to create a new dict_init_values base
    for key, value in dict_init_values.items():
        init_keys.append(key)
    for key, value in submitted_data.items():
        action_id = list(value.keys())[0]
        if action_id not in init_keys:
            raise Exception(f"key {action_id} not in init_keys:{init_keys}")
        if action_id == "sf_template_name_id":
            dict_init_values[action_id]["value"] = value[action_id]["value"]
        elif action_id == "Edit_templates":
            if len(list(value[action_id]["selected_options"])) > 0:
                dict_init_values[action_id]["value"] = True
            else:
                dict_init_values[action_id]["value"] = False
        elif action_id == "template":
            dict_init_values[action_id]["value"] = value[action_id]["selected_option"]["value"].replace(" ", "_")
        elif action_id == "folder_1":
            dict_init_values[action_id]["value"] = value[action_id]["selected_option"]["value"].replace(" ", "_")
        elif action_id == "folder_2":
            dict_init_values[action_id]["value"] = value[action_id]["selected_option"]["value"].replace(" ", "_")
        elif action_id == "variables":
            dict_init_values[action_id]["value"] = value[action_id]["selected_option"]["value"].replace(" ", "_")
        elif action_id == "prompt_quickeditor":
            if len(list(value[action_id]["selected_options"])) > 0:
                dict_init_values[action_id]["value"] = True
            else:
                dict_init_values[action_id]["value"] = False
        elif action_id == "prompt_queue_checkbox":
            if len(list(value[action_id]["selected_options"])) > 0:
                dict_init_values[action_id]["value"] = True
            else:
                dict_init_values[action_id]["value"] = False
        elif action_id == "writing_instructions":
            dict_init_values[action_id]["value"] = value[action_id]["value"]
        elif action_id == "model":
            dict_init_values[action_id]["value"] = value[action_id]["selected_option"]["value"]
        elif action_id == "temperature":
            dict_init_values[action_id]["value"] = value[action_id]["value"]
        elif action_id == "samples":
            dict_init_values[action_id]["value"] = value[action_id]["value"]
        # if "_buttons" is in the last part of the action_id string, then we need to set visable to True
        # elif action_id.endswith("_buttons"):
        #     dict_init_values[action_id]["visable"] = True
        elif action_id.endswith("_prompt"):
            dict_init_values[action_id]["value"] = value[action_id]["value"]
        elif action_id.endswith("_rename"):
            dict_init_values[action_id]["value"] = value[action_id]["value"]
        elif action_id.startswith("new_") and action_id.endswith("_name"):
            dict_init_values[action_id]["value"] = value[action_id]["value"]
        elif action_id.startswith("start/copy_from_"):
            dict_init_values[action_id]["value"] = value[action_id]["selected_option"]["value"]
        elif action_id == "preview_checkbox":
            if len(list(value[action_id]["selected_options"])) > 0:
                dict_init_values[action_id]["value"] = True
            else:
                dict_init_values[action_id]["value"] = False

    print('dict_init_values["template"]["visable"]', dict_init_values["template"]["visable"])
    print("action_taken:", action_taken)
    print('dict_init_values["template_buttons"]["visable"]', dict_init_values["template_buttons"]["visable"])
    # resolve the action. Ask yourself, what only happens when this action is taken?
    if action_taken:
        # when prompt_queue_checkbox is checked, make model, temperature, and samples invisible
        if action_taken == "prompt_queue_checkbox":
            if dict_init_values["prompt_queue_checkbox"]["value"] is True:
                dict_init_values["model"]["visable"] = False
                dict_init_values["temperature"]["visable"] = False
                dict_init_values["samples"]["visable"] = False
            else:
                dict_init_values["model"]["visable"] = True
                dict_init_values["temperature"]["visable"] = True
                dict_init_values["samples"]["visable"] = True
        # for key in init_keys:
        if action_taken == "Edit_templates":
            if dict_init_values["Edit_templates"]["value"] == True:
                for key in dict_init_values.keys():
                    if "_buttons" in key:
                        folders = ["template", "folder_1", "folder_2", "variables"]
                        for folder in folders:
                            if key.startswith(folder) and dict_init_values[folder]["visable"]:
                                dict_init_values[key]["visable"] = True
                    elif "start/copy_from_"  in key or "_prompt" in key or "_save_button" in key or "_rename" in key or ("new_" in key and "_name" in key):
                        dict_init_values[key]["visable"] = False
                
        elif action_taken in ["template"]:
            # dict_init_values["preview_checkbox"]["value"] = False
            if dict_init_values["template"]["value"] == "None":
                dict_init_values["Edit_templates"]["value"] = False
                # shut off every key that contains folder_1, folder_2, and variables
                for key in dict_init_values.keys():
                    if "folder_1" in key or "folder_2" in key or "variables" in key:
                        dict_init_values[key]["visable"] = False
            else:
                # turn on just the base folder_1?
                dict_init_values["Edit_templates"]["value"] = False
                dict_init_values["folder_1"]["visable"] = True
                dict_init_values["folder_2"]["visable"] = True
                # import code; code.interact(local=dict(globals(), **locals()))
            # dict_init_values["Edit_templates"]["visable"] = True
        elif action_taken in ["folder_1", "folder_2", "variables"]:
            # dict_init_values["preview_checkbox"]["value"] = False
            if action_taken in ["folder_1", "folder_2", "variables"]:
                # make invisible everything in that section except for the base action_taken
                for key in dict_init_values.keys():
                    if action_taken in key and "_buttons" not in key and key != action_taken and key != "Edit_templates":
                        dict_init_values[key]["visable"] = False
        elif action_taken == "preview_checkbox":
            # toggle the preview text display
            if dict_init_values["preview_checkbox"]["value"] is False:
                dict_init_values["preview"]["visable"] = False
                # remove every key with preview in the key except for preview_checkbox and preview
                for key in dict_init_values.keys():
                    if "preview" in key and key != "preview_checkbox" and key != "preview":
                        # delete the key from the dict
                        # del dict_init_values[key]
                        dict_init_values[key]["visable"] = False
            else:
                dict_init_values["preview"]["visable"] = True
        elif action_taken.endswith("_button_delete") and \
                    dict_init_values[action_taken[:-14]]["value"] != "None":
            # dict_init_values["start/copy_from_"+action_taken[:-14]]["visable"] = False
            # delete the infered folder and txt file pair
            # infer the path to the prompt
            file_path = folder_path
            if action_taken.startswith("variables"):
                base_folder_search = os.path.join(file_path, dict_init_values["template"]["value"])
                file_path = os.path.join(file_path, dict_init_values["template"]["value"], "vars")
                # remove the txt file but not the folder
                if dict_init_values[action_taken[:-14]]["value"] != "None":
                    os.remove(os.path.join(file_path, dict_init_values[action_taken[:-14]]["value"] + ".txt"))
            else:
                for value in [dict_init_values["template"]["value"], dict_init_values["folder_1"]["value"], dict_init_values["folder_2"]["value"]]:
                    if value == dict_init_values[action_taken[:-14]]["value"]:
                        base_folder_search = file_path
                        file_path = os.path.join(file_path, dict_init_values[action_taken[:-14]]["value"])
                        break
                    elif value != "None":
                        file_path = os.path.join(file_path, value)
                # remove the file and then the folder
                if dict_init_values[action_taken[:-14]]["value"] != "None":
                    shutil.rmtree(file_path)
            # set the value to a different folder or None if there are no other folders
            # get the list of folders (exclude files)
            if action_taken[:-14] == "variables":
                base_folder_search = os.path.join(base_folder_search, "vars")
                folders = [f for f in os.listdir(base_folder_search) if os.path.isdir(os.path.join(base_folder_search, f))]
                if len(folders) > 0:
                    dict_init_values[action_taken[:-14]]["value"] = folders[0]
                else:
                    dict_init_values[action_taken[:-14]]["value"] = "None"
            else:
                folders = [f for f in os.listdir(base_folder_search) if os.path.isdir(os.path.join(base_folder_search, f))]
                # remove the vars folder
                folders = [f for f in folders if f != "vars"]
                if len(folders) > 0:
                    dict_init_values[action_taken[:-14]]["value"] = folders[0]
                else:
                    dict_init_values[action_taken[:-14]]["value"] = "None"
            # import code; code.interact(local=dict(globals(), **locals()))
            # turn off the visable for the action_taken varients. Except for the base action_taken
            for key in dict_init_values.keys():
                if action_taken[:-14] in key and key != action_taken[:-14] and \
                    key != "Edit_templates" and "_buttons" not in key:
                    dict_init_values[key]["visable"] = False

            if dict_init_values["template"]["value"] == "None":
                # make the base folder_1, folder_2, and variables invisable
                for key in dict_init_values.keys():
                    if key != "Edit_templates" and ("folder_1" in key or "folder_2" in key or "variables" in key):
                        dict_init_values[key]["visable"] = False
                dict_init_values["Edit_templates"]["value"] = False
                # dict_init_values["Edit_templates"]["visable"] = True

        elif action_taken.endswith("_button_prompt") and dict_init_values[action_taken[:-14] + "_buttons"]["visable"]:
            # print('dict_init_values[action_taken[:-14] + "_buttons"]["visable"]', dict_init_values[action_taken[:-14] + "_buttons"]["visable"])
            # print('not dict_init_values["new_"+action_taken[:-14]+"_name"]["visable"]', not dict_init_values["new_"+action_taken[:-14]+"_name"]["visable"])
            # print('dict_init_values[action_taken[:-14] + "_prompt"]["visable"]', dict_init_values[action_taken[:-14] + "_prompt"]["visable"])
            
            # toggle the visable for this prompt quickeditor
            if (dict_init_values[action_taken[:-14] + "_prompt"]["visable"] and \
                not dict_init_values["new_"+action_taken[:-14]+"_name"]["visable"]) or \
                    dict_init_values[action_taken[:-14]]["value"] == "None":
                dict_init_values[action_taken[:-14] + "_prompt"]["visable"] = False
                dict_init_values[action_taken[:-14] + "_save_button"]["visable"] = False
            else:
                dict_init_values[action_taken[:-14] + "_prompt"]["visable"] = True
                dict_init_values[action_taken[:-14] + "_save_button"]["visable"] = True
                # infer the path to the prompt
                file_path = folder_path
                if action_taken.startswith("variables"):
                    file_path = os.path.join(file_path, dict_init_values["template"]["value"], "vars", dict_init_values["variables"]["value"] + ".txt")
                else:
                    for value in [dict_init_values["template"]["value"], dict_init_values["folder_1"]["value"], dict_init_values["folder_2"]["value"]]:
                        if value == dict_init_values[action_taken[:-14]]["value"]:
                            file_path = os.path.join(file_path, dict_init_values[action_taken[:-14]]["value"], dict_init_values[action_taken[:-14]]["value"] + ".txt")
                            break
                        elif value != "None":
                            file_path = os.path.join(file_path, value)

                # write the contents of the prompt to the file
                with open(file_path, "r") as f:
                    button_saved_prompt = f.read()

                dict_init_values[action_taken[:-14] + "_prompt"]["value"] = button_saved_prompt
            dict_init_values[action_taken[:-14] + "_rename"]["visable"] = False
            dict_init_values["new_"+action_taken[:-14]+"_name"]["visable"] = False
            if not action_taken[:-14] == "variables":
                dict_init_values["start/copy_from_"+action_taken[:-14]]["visable"] = False
            # print(dict_init_values[action_taken[:-14] + "_prompt"])
            # print(dict_init_values[action_taken[:-14] + "_save_button"])
            # import code; code.interact(local=dict(globals(), **locals()))
        # if _info is in the last part of the action_id string, then we need to set visable to True
        elif action_taken.endswith("_info") and dict_init_values[action_taken[:-12] + "_buttons"]["visable"]:
            # toggle the visable
            if dict_init_values[action_taken[:-12] + "_info"]["visable"]:
                dict_init_values[action_taken[:-12] + "_info"]["visable"] = False
            else:
                dict_init_values[action_taken[:-12] + "_info"]["visable"] = True
        elif action_taken.endswith("_button_Save_changes"):
            if dict_init_values[action_taken[:-20] + "_prompt"]["visable"] and \
                dict_init_values["new_"+action_taken[:-20]+"_name"]["visable"] is False:
                # make the prompt and this button invisible and save the contents of the prompt to the file
                dict_init_values[action_taken[:-20] + "_prompt"]["visable"] = False
                dict_init_values[action_taken[:-20] + "_save_button"]["visable"] = False
                # save the contents of the prompt to the file
                # get the contents of the prompt
                # prompt_contents = dict_init_values[action_taken[:-20] + "_prompt"]["value"]
                # get the file path by infering it from dict_init_values and action_taken
                file_path = folder_path
                if action_taken.startswith("variables"):
                    file_path = os.path.join(file_path, dict_init_values["template"]["value"], "vars", dict_init_values["variables"]["value"] + ".txt")
                else:
                    for value in [dict_init_values["template"]["value"], dict_init_values["folder_1"]["value"], dict_init_values["folder_2"]["value"]]:
                        if value == dict_init_values[action_taken[:-20]]["value"]:
                            file_path = os.path.join(file_path, dict_init_values[action_taken[:-20]]["value"], dict_init_values[action_taken[:-20]]["value"] + ".txt")
                            break
                        elif value != "None":
                            file_path = os.path.join(file_path, value)

                # write the contents of the prompt to the file
                with open(file_path, "w") as f:
                    f.write(dict_init_values[action_taken[:-20] + "_prompt"]["value"])
            elif dict_init_values[action_taken[:-20] + "_prompt"]["visable"] and \
                dict_init_values["new_"+action_taken[:-20]+"_name"]["visable"] is True:
                dict_init_values[action_taken[:-20] + "_prompt"]["visable"] = False
                dict_init_values[action_taken[:-20] + "_save_button"]["visable"] = False
                dict_init_values["new_"+action_taken[:-20]+"_name"]["visable"] = False
                set_folder_name = dict_init_values["new_"+action_taken[:-20]+"_name"]["value"]
                set_folder_name = set_folder_name.replace(" ", "_")

                if not action_taken[:-20] == "variables":
                    dict_init_values["start/copy_from_"+action_taken[:-20]]["visable"] = False
                file_path = folder_path
                if action_taken.startswith("variables"):
                    file_path = os.path.join(file_path, dict_init_values["template"]["value"], "vars", set_folder_name + ".txt")
                else:
                    for value in [dict_init_values["template"]["value"], dict_init_values["folder_1"]["value"], dict_init_values["folder_2"]["value"]]:
                        if value == dict_init_values[action_taken[:-20]]["value"]:  # need new stopping statement
                            file_path = os.path.join(file_path, set_folder_name, set_folder_name + ".txt")
                            break
                        elif value != "None":
                            file_path = os.path.join(file_path, value)
                # need to make a new folder at file_path named dict_init_values["new_"+action_taken[:-20]+"_name"]["value"]
                # also a txt file called dict_init_values["new_"+action_taken[:-20]+"_name"]["value"]+".txt"
                # fill the txt file with the contents of the prompt
                # Ensure all directories in file_path exist
                dir_path = os.path.dirname(file_path)
                os.makedirs(dir_path, exist_ok=True)

                with open(file_path, "w") as f:
                    f.write(dict_init_values[action_taken[:-20] + "_prompt"]["value"])
                if action_taken[:-20] == "template":
                    dict_init_values["Edit_templates"]["value"] = False
                    dict_init_values["template"]["value"] = set_folder_name

            elif dict_init_values[action_taken[:-20] + "_rename"]["visable"]:
                dict_init_values[action_taken[:-20] + "_rename"]["visable"] = False
                dict_init_values[action_taken[:-20] + "_save_button"]["visable"] = False
                dict_init_values["new_"+action_taken[:-20]+"_name"]["visable"] = False
                new_name = dict_init_values[action_taken[:-20] + "_rename"]["value"]
                new_name = new_name.replace(" ", "_")
                if new_name.startswith("vars_"):
                    new_name = new_name[5:]
                file_path = folder_path
                if action_taken.startswith("variables"):
                    file_path = os.path.join(file_path, dict_init_values["template"]["value"], "vars", dict_init_values["variables"]["value"] + ".txt")
                else:
                    for value in [dict_init_values["template"]["value"], dict_init_values["folder_1"]["value"], dict_init_values["folder_2"]["value"]]:
                        if value == dict_init_values[action_taken[:-20]]["value"]:
                            file_path = os.path.join(file_path, dict_init_values[action_taken[:-20]]["value"], dict_init_values[action_taken[:-20]]["value"] + ".txt")
                            break
                        elif value != "None":
                            file_path = os.path.join(file_path, value)
                # rename the file.txt and the folder above it to the new name. BOTH OF THEM are renamed to new_name
                # file_path ends in old_name/old_name.txt where old_name is the old name of the file/folder
                # Now, rename the file and the folder above it to the new name
                old_folder_path, old_file_name = os.path.split(file_path)

                # Extract the old_name without the file extension
                old_name = os.path.splitext(old_file_name)[0]

                # Check if folder name and file name (without extension) are the same
                if os.path.basename(old_folder_path) != old_name:
                    if os.path.basename(old_folder_path) == 'vars' and old_name.startswith('var_'):
                        # This is a variable file inside the 'vars' folder.
                        # Only rename the file, not the folder
                        new_file_path = os.path.join(old_folder_path, "var_" + new_name + ".txt")
                        os.rename(file_path, new_file_path)
                    else:
                        raise ValueError("The folder and file names are not the same")
                else:
                    new_folder_path = os.path.join(os.path.dirname(old_folder_path), new_name)
                    new_file_path = os.path.join(new_folder_path, new_name + ".txt")
                    
                    # Rename the folder
                    os.rename(old_folder_path, new_folder_path)
                    # import code; code.interact(local=dict(globals(), **locals()))
                    # Rename the file inside the renamed folder
                    os.rename(os.path.join(new_folder_path, old_name+".txt"), new_file_path)
                    # check for old_folder_path existence
                    # if os.path.exists(old_folder_path):
                # adjust the value fields of template, folder_1, folder_2 or variables (whichever was renamed)
                value_fields = ["template", "folder_1", "folder_2", "variables"]
                for value_field in value_fields:
                    if dict_init_values[value_field]["value"] == old_name:
                        dict_init_values[value_field]["value"] = new_name
                        break
                # import code; code.interact(local=dict(globals(), **locals()))       
            elif dict_init_values["new_"+action_taken[:-20]+"_name"]["visable"] and \
                dict_init_values[action_taken[:-20] + "_prompt"]["visable"]:
                dict_init_values[action_taken[:-20] + "_prompt"]["visable"] = False
                dict_init_values["new_"+action_taken[:-20]+"_name"]["visable"] = False
                dict_init_values[action_taken[:-20] + "_save_button"]["visable"] = False
                # create a new folder with the new prompt name at the infered path
                # put the value of the prompt into a txt file in the new folder
                # name the txt file the same as the folder but with a .txt extension
                # adjust the value fields of template, folder_1, folder_2 or variables (whichever was added to)
                new_name = dict_init_values["new_"+action_taken[:-20]+"_name"]["value"]
                new_name = new_name.replace(" ", "_")
                if action_taken == "new_variables_name":
                    if not new_name.startswith("var_"):
                        new_name = "var_" + new_name
                    else:
                        new_name = "var_" + new_name
                    if new_name == "var_":
                        # append a ts to the end of the name to make it unique
                        new_name = new_name + str(int(time.time())).split('.')[1]
                    # don't create a new folder, just create a new file in the vars folder
                    file_path = os.path.join(folder_path, "vars", "var_" + new_name + ".txt")
                    with open(file_path, "w") as f:
                        f.write(dict_init_values[action_taken[:-20] + "_prompt"]["value"])
                    dict_init_values["variables"]["value"] = new_name
                else:
                    file_path = folder_path
                    # this is infers the path to the new folder from the values of template, folder_1, folder_2
                    for value in [dict_init_values["template"]["value"], dict_init_values["folder_1"]["value"], dict_init_values["folder_2"]["value"]]:
                        if value == dict_init_values[action_taken[:-20]]["value"]:
                            file_path = os.path.join(file_path, new_name, new_name + ".txt")
                            break
                        elif value != "None":
                            file_path = os.path.join(file_path, value)
                    # create the new folder
                    os.mkdir(os.path.dirname(file_path))
                    # create the new file
                    with open(file_path, "w") as f:
                        f.write(dict_init_values[action_taken[:-20] + "_prompt"]["value"])
                    dict_init_values[action_taken[:-20]]["value"] = new_name
                dict_init_values[action_taken[:-20] + "_prompt"]["value"] = ""

        elif action_taken.endswith("_button_rename") and \
                    dict_init_values[action_taken[:-14]]["value"] != "None":
            # turn off the prompt and create new then turn on the save button
            dict_init_values[action_taken[:-14]+"_prompt"]["visable"] = False
            dict_init_values["new_"+action_taken[:-14]+"_name"]["visable"] = False
            if not action_taken[:-14] == "variables":
                dict_init_values["start/copy_from_"+action_taken[:-14]]["visable"] = False
            dict_init_values[action_taken[:-14]+"_save_button"]["visable"] = True
            # toggle the visable
            if dict_init_values[action_taken[:-14]+"_rename"]["visable"]:
                dict_init_values[action_taken[:-14]+"_rename"]["visable"] = False
                dict_init_values[action_taken[:-14]+"_save_button"]["visable"] = False
            else:
                dict_init_values[action_taken[:-14]+"_rename"]["visable"] = True
                dict_init_values[action_taken[:-14]+"_save_button"]["visable"] = True
            base_name = action_taken[:-14]
            dict_init_values[action_taken[:-14]+"_rename"]["value"] = dict_init_values[base_name]["value"]
        elif action_taken.endswith("_button_create_new"):
            key_ = "new_"+action_taken[:-18]+"_name"
            # turn off the prompt and rename then turn on the save button
            dict_init_values[action_taken[:-18]+"_rename"]["visable"] = False
            # toggle the visable
            if dict_init_values[key_]["visable"]:
                dict_init_values[key_]["visable"] = False
                dict_init_values[action_taken[:-18]+"_save_button"]["visable"] = False
                dict_init_values[action_taken[:-18]+"_prompt"]["visable"] = False
                if not action_taken[:-18] == "variables":
                    dict_init_values["start/copy_from_"+action_taken[:-18]]["visable"] = False
            else:
                dict_init_values[key_]["visable"] = True
                dict_init_values[action_taken[:-18]+"_save_button"]["visable"] = True
                if not action_taken[:-18] == "variables":
                    dict_init_values["start/copy_from_"+action_taken[:-18]]["visable"] = True
                dict_init_values[action_taken[:-18]+"_prompt"]["visable"] = True
                dict_init_values[action_taken[:-18]+"_prompt"]["value"] = " "
        elif action_taken.startswith("start/copy_from_"):
            # copy selected folder to the new folder, renaming it to the value of "new_"+action_taken[16:]+"_name"
            set_folder_name = dict_init_values["new_"+action_taken[16:]+"_name"]["value"]
            set_folder_name = set_folder_name.replace(" ", "_")
            chosen_folder = dict_init_values["start/copy_from_"+action_taken[16:]]["value"]
            chosen_folder = chosen_folder.replace(" ", "_")

            if set_folder_name == "_":  # don't change anything
                pass
            else:
                # recursively search folder_path tree for the folder that matches chosen_folder
                # def find_folder(folder_path, chosen_folder):
                #     for root, dirs, _ in os.walk(folder_path):
                #         if chosen_folder in dirs:
                #             return os.path.join(root, chosen_folder)
                #     raise Exception(f"folder {chosen_folder} not found in", folder_path)
                
                # old_file_path = find_folder(folder_path, chosen_folder)
                # new_file_path_minus_last_segment = os.path.join(folder_path, "vars")
                file_path = folder_path
                for value in [dict_init_values["template"]["value"], dict_init_values["folder_1"]["value"], dict_init_values["folder_2"]["value"]]:
                    # search for the folder that matches chosen_folder
                    dirs = [d for d in os.listdir(file_path) if os.path.isdir(os.path.join(file_path, d))]
                    # print("dirs: ", dirs)
                    if chosen_folder in dirs:  # dict_init_values[action_taken[16:]]["value"]
                        new_file_path_minus_last_segment = file_path
                        old_file_path = os.path.join(file_path, chosen_folder)
                        old_folder_txt = os.path.join(file_path, value, value+".txt")
                        old_txt_name = value + ".txt"
                        break
                    elif value != "None":
                        file_path = os.path.join(file_path, value)

                new_file_path = os.path.join(new_file_path_minus_last_segment, set_folder_name)
                # create the new folder
                if os.path.exists(new_file_path):
                    shutil.rmtree(new_file_path)
                # print(os.path.exists(old_file_path + "/Faith_and_Freedom.txt"))
                # recursively copy the contents of the old folder to the new folder
                shutil.copytree(old_file_path, new_file_path)
                # print(os.path.exists(old_folder_txt))
                # import code; code.interact(local=dict(globals(), **locals()))
                # rename the txt file in the new folder
                os.rename(os.path.join(new_file_path, old_txt_name), os.path.join(new_file_path, set_folder_name+".txt"))
                
                # print(os.path.exists(old_folder_txt))
                dict_init_values[action_taken[16:]]["value"] = set_folder_name
                dict_init_values["new_"+action_taken[16:]+"_name"]["value"] = " "
                dict_init_values["new_"+action_taken[16:]+"_name"]["visable"] = False
                dict_init_values["start/copy_from_"+action_taken[16:]]["visable"] = False
                dict_init_values[action_taken[16:]+"_save_button"]["visable"] = False
                dict_init_values[action_taken[16:]+"_prompt"]["visable"] = False
                # dict_init_values[action_taken[16:]+"_save_button"]["visable"] = True  # doesn't work
                dict_init_values["Edit_templates"]["value"] = False
                # import code; code.interact(local=dict(globals(), **locals()))
    
    # condionals that are always applied
    if dict_init_values["Edit_templates"]["value"] == False:
        dict_init_values["variables"]["visable"] = False
        for key in dict_init_values.keys():
            id_frags = ["_buttons", "_prompt", "_save_button", 
                        "_button_rename", "_rename", "_button_create_new", 
                        "_info", "_button_prompt", "new_", "start/copy_from_"]
            for frag in id_frags:
                if frag in key:
                    dict_init_values[key]["visable"] = False
    else:
        # make sure the base value_field buttons are visable
        for key in dict_init_values.keys():
            id_frags = ["_buttons"]
            for frag in id_frags:
                if frag in key:
                    dict_init_values[key]["visable"] = True
            if key in ["template", "folder_1", "folder_2", "variables"]:
                dict_init_values[key]["visable"] = True
        # if variables value is not a .txt file in vars then set it to None
        if dict_init_values["template"]["value"] == "None":  # make all base value_fields + buttons invisable
            for key in dict_init_values.keys():
                id_frags = ["_buttons"]
                for frag in id_frags:
                    if frag in key and key != "template_buttons":
                        dict_init_values[key]["visable"] = False
                if key in ["folder_1", "folder_2", "variables"]:
                    dict_init_values[key]["visable"] = False

    if dict_init_values["template"]["value"] != "None":
        if is_adjacent(folder_path, dict_init_values["template"]["value"], dict_init_values["folder_1"]["value"]):
            dict_init_values["folder_1"]["visable"] = True
        else:
            # # need to find logical defaults for the value fields of folder_1 and folder_2
            
            # find the first folder in folder_path that is not named vars AND is adjacent to dict_init_values["template"]["value"]
            # AND peferably has a subfolder (folder_2) that is adjacent to it
            folder_candidates = {}
            for root, dirs, _ in os.walk(folder_path):
                for dir_name in dirs:
                    if dir_name != 'vars' and is_adjacent(folder_path, dict_init_values["template"]["value"], dir_name):
                        # check if there is a subfolder that is adjacent to dir_name
                        # if so then add dir_name to the start of folder_candidates
                        # else add dir_name to the end of folder_candidates
                        subfolder_candidates = []
                        for root2, dirs2, _ in os.walk(os.path.join(root, dir_name)):
                            for dir_name2 in dirs2:
                                if dir_name2 != 'vars' and is_adjacent(folder_path, dir_name, dir_name2):
                                    subfolder_candidates.append(dir_name2)
                        if len(subfolder_candidates) > 0:
                            folder_candidates[dir_name] = subfolder_candidates
                        else:
                            folder_candidates[dir_name] = []
            
            # if there are no folder candidates, then set folder_1 and 2 to "None", f1 visable to True and f2 visable to False
            if len(folder_candidates) == 0:
                dict_init_values["folder_1"]["value"] = "None"
                dict_init_values["folder_2"]["value"] = "None"
                dict_init_values["folder_1"]["visable"] = True
                dict_init_values["folder_2"]["visable"] = False
            else:
                # take the first folder_candidate and set folder_1 to it
                dict_init_values["folder_1"]["value"] = list(folder_candidates.keys())[0]
                # if there are subfolder_candidates, then set folder_2 to the first one
                if len(folder_candidates[dict_init_values["folder_1"]["value"]]) > 0:
                    dict_init_values["folder_2"]["value"] = folder_candidates[dict_init_values["folder_1"]["value"]][0]
                else:
                    dict_init_values["folder_2"]["value"] = "None"
                dict_init_values["folder_1"]["visable"] = True
                dict_init_values["folder_2"]["visable"] = True



            # import code; code.interact(local=dict(globals(), **locals()))


            # if there is no folder_2, then just show the first folder_1 and set folder_2 to "None" and folder_2 visable to True


        # else:
        #     dict_init_values["folder_1"]["visable"] = True
        #     dict_init_values["folder_2"]["visable"] = True

        if is_adjacent(folder_path, dict_init_values["folder_1"]["value"], dict_init_values["folder_2"]["value"]):
            dict_init_values["folder_2"]["visable"] = True
        else:
            dict_init_values["folder_2"]["visable"] = False

        # find default values for folder_1 and folder_2
        combined_path = os.path.join(folder_path, dict_init_values["template"]["value"])
        # check if combined_path exists at all
        if os.path.exists(combined_path):
            if dict_init_values["folder_1"]["visable"] == False:
                # if there is at least one folder not named vars in folder_path combined with dict_init_values["template"]["value"], then we need to show one in the folder_1 dropdown. Else show "None" in folder_1
                # combine folder_path with dict_init_values["template"]["value"]
                # get all the directories in combined_path
                combined_path_dirs = [f for f in os.listdir(combined_path) if os.path.isdir(os.path.join(combined_path, f))]
                # remove the vars folder if it exists
                if "vars" in combined_path_dirs:
                    combined_path_dirs.remove("vars")
                # if there are no directories left, then we need to show "None" in folder_1
                if len(combined_path_dirs) == 0:
                    dict_init_values["folder_1"]["value"] = "None"
                    dict_init_values["folder_2"]["visable"] = False
                    # turn off the folder_2_buttons as well
                    for key in dict_init_values.keys():
                        if "folder_2" in key:
                            dict_init_values[key]["visable"] = False
                else:
                    dict_init_values["folder_1"]["value"] = combined_path_dirs[0]
                if dict_init_values["Edit_templates"]["value"] is False and \
                    dict_init_values["folder_1"]["value"] == "None":
                    dict_init_values["folder_1"]["visable"] = False
                else:
                    dict_init_values["folder_1"]["visable"] = True
                
            if dict_init_values["folder_2"]["visable"] == False and dict_init_values["folder_1"]["value"] != "None":
                # same as above, but for folder_2. I'll just write a function for this here
                combined_path = os.path.join(folder_path, dict_init_values["template"]["value"], dict_init_values["folder_1"]["value"])
                combined_path_dirs = [f for f in os.listdir(combined_path) if os.path.isdir(os.path.join(combined_path, f))]
                if "vars" in combined_path_dirs:
                    combined_path_dirs.remove("vars")
                if len(combined_path_dirs) == 0:
                    dict_init_values["folder_2"]["value"] = "None"
                else:
                    dict_init_values["folder_2"]["value"] = combined_path_dirs[0]
                dict_init_values["folder_2"]["visable"] = True
            elif dict_init_values["folder_2"]["visable"] == False and dict_init_values["folder_1"]["value"] == "None":
                # turn off the folder_2_buttons
                for key in dict_init_values.keys():
                    if "folder_2" in key:
                        dict_init_values[key]["visable"] = False

        
    for key in dict_init_values.keys():
        # if the button parent's value is "None" then just make the first button visable
        if dict_init_values["template"]["value"] != "None" and "_buttons" in key:
            # and variables_path contains at least one file 
            if dict_init_values[key]["value"] == "None" and not len(os.listdir(variables_path)) > 0:
                # remove all elements from the list except the first one
                dict_init_values[key]["value"] = [dict_init_values[key]["value"][0]]
                dict_init_values[key]["action_id"] = [dict_init_values[key]["action_id"][0]]
            else:
                # rebuild the list of buttons from button_states and key[:-8]
                # save corresponding lists to value and action_id
                if key == "template_buttons":
                    new_state = list(button_states[0])  # Create a copy of the list
                    new_state[0] = "new_client"         # Modify the copy
                    dict_init_values[key]["value"] = new_state  # Assign the modified copy
                else:
                    dict_init_values[key]["value"] = button_states[0]  # Assign the original list

                # generate the action_id from the key[:-8] and the button_states[2] (the function)
                dict_init_values[key]["action_id"] = button_states[2](key[:-8], button_states[1])
    # if the preview_checkbox value is False then remove all preview keys
    if dict_init_values["preview_checkbox"]["value"] is False:
        # remove every key with preview in the key except for preview_checkbox and preview
        for key in dict_init_values.keys():
            if "preview" in key and key != "preview_checkbox":
                dict_init_values[key]["visable"] = False
    # if the preview_checkbox value is True then make all preview keys visable
    else:
        for key in dict_init_values.keys():
            if "preview" in key:
                dict_init_values[key]["visable"] = True
    print(dict_init_values)
    # import code; code.interact(local=dict(globals(), **locals()))
    return dict_init_values

def is_adjacent(base_path, folder1, folder2):
    # Check if base_path exists and is a directory
    if not os.path.isdir(base_path):
        return False
    # Iterate through the directories
    for root, dirs, _ in os.walk(base_path):
        # print(root, dirs, _)
        # Check if folder1 is a part of the current path
        if folder1 in root:
            # Check if folder2 is a direct subdirectory of folder1
            for dir_name in dirs:
                # Construct full path
                full_path = os.path.join(root, dir_name)
                # Check if it matches folder2 as direct subdirectory of folder1
                if dir_name == folder2 and folder1 in full_path:
                    relative_path = os.path.relpath(full_path, root)
                    if relative_path == folder2:
                        return True
    # If the loop completes without returning True, return False
    return False

async def generate_csv_file(articles, column_title="articles"):
    csv_file = f"articles.csv"
    async with aiofiles.open(csv_file, "w", newline='', encoding='utf-8') as file:
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_ALL)

        # Write the column title
        writer.writerow([column_title])

        # Write the articles
        for article in articles:
            writer.writerow([article])
        csv_content = output.getvalue()
        await file.write(csv_content)
    return csv_file
    
def zip_folder(folder_path):
    """
    Compresses the contents of a folder into a zip file while preserving the directory structure.
    
    Parameters:
    folder_path (str): Path to the folder to be zipped.
    
    Returns:
    str: Path to the created ZIP file.
    """
    zip_path = folder_path + '.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, os.path.relpath(file_path, folder_path))

    return zip_path





def parse_markdown_ordered_list(md_text):
    def extract_item_info(line):
        # Extracts the count and the start of instruction from a line
        number, instruction_start = line.strip().split('. ', 1)
        return number, instruction_start

    def parse_list(lines):
        # Parses the list to form the final structured list
        parsed_list = []
        current_item = None
        current_text = []

        for line in lines:
            if line.strip() and line[0].isdigit():
                # Start of a new list item
                if current_item:
                    # Add the previous item to the list
                    instruction = ' '.join(current_text).strip()
                    parsed_list.append({
                        'metadata': {'count': current_item},
                        'instruction': instruction,
                        'details': []  # No nested details as per new format
                    })
                    current_text = []

                current_item, instruction_start = extract_item_info(line)
                current_text.append(instruction_start)
            elif current_item:
                # Continuation of the current list item
                current_text.append(line.strip())

        # Add the last item to the list
        if current_item:
            instruction = ' '.join(current_text).strip()
            parsed_list.append({
                'metadata': {'count': current_item},
                'instruction': instruction,
                'details': []  # No nested details as per new format
            })

        return parsed_list

    lines = md_text.strip().split('\n')
    return parse_list(lines)



if __name__ == "__main__":
    # Example usage
    md_text = """
starting text before list

1. First item
    1. Subitem 
        1. Subsubitem 
    2. Subitems (or any item) can have multiple lines
       and still be part of the same list item
2. Second item
    1. Subitem 
    2. Subitem 
3. Third item

text after list
"""

    parsed_list = parse_markdown_ordered_list(md_text)
    for item in parsed_list:
        print(item)



# desired output format reminder:

# [
#     {
#         "metadata": {"count": "1"},
#         "instruction": """First item
#     1. Subitem 
#         1. Subsubitem 
#     2. Subitems (or any item) can have multiple lines
#        and still be part of the same list item""",
#         "details": []
#     },
#     {
#         "metadata": {"count": "2"},
#         "instruction": """Second item
#     1. Subitem 
#     2. Subitem """,
#         "details": []
#     },
#     {
#         "metadata": {"count": "3"},
#         "instruction": "Third item",
#         "details": []
#     }
# ]



"""
desired output format reminder:

[
    {
        "metadata": {"count": "1"},
        "instruction": "First item",
        "details": [
            {
                "metadata": {"count": "1.1"},
                "instruction": "Subitem",
                "details": [
                    {
                        "metadata": {"count": "1.1.1"},
                        "instruction": "Subsubitem",
                        "details": []
                    }
                ]
            },
            {
                "metadata": {"count": "1.2"},
                "instruction": "Subitems (or any item) can have multiple lines and still be part of the same list item",
                "details": []
            }
        ]
    },
    {
        "metadata": {"count": "2"},
        "instruction": "Second item",
        "details": [
            {
                "metadata": {"count": "2.1"},
                "instruction": "Subitem",
                "details": []
            },
            {
                "metadata": {"count": "2.2"},
                "instruction": "Subitem",
                "details": []
            }
        ]
    },
    {
        "metadata": {"count": "3"},
        "instruction": "Third item",
        "details": []
    }
]"""
