from io import BytesIO, StringIO
import copy, logging, pickle, asyncio, json, zipfile, tempfile, os
import aiohttp, redis, csv, traceback, time, io, aiofiles, shutil, sys
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError
from pathlib import Path
from dotenv import load_dotenv


# python async_server.py --env=.env.savant.dev --channel=s --redis_host=False --slack_log_channel=error-logs
# python async_server.py --env=.env.wordle --channel=pytesting --redis_host=False --slack_log_channel=error-logs
# python async_server.py --env=.env.savant.dev --channel=savant-staging --redis_host=False --slack_log_channel=error-logs
# get the env file flag from the cmd. By default, it is None. If it is not None, then load the file called .env
# how to list conda environments: conda env list
# how to activate conda env: conda activate env_name

"""
no en

lo
virbro
br-long_hex_number
veth-hex_number@if30

"""
env_file = None
redis_host = False
slack_log_channel = None
for arg in sys.argv:
    if arg.startswith('--env='):
        env_file = arg.split('=')[1]
    if arg.startswith('--channel='):
        channel = arg.split('=')[1]
    if arg.startswith('--slack_log_channel='):
        slack_log_channel = arg.split('=')[1]
    if arg.startswith('--redis_host='):
        var = arg.split('=')[1]
        if var in['true', 'True']:
            redis_host = True
if env_file is not None:
    # this is to hide the print statement from multiprocessing forks
    if __name__ == "__main__": print(f"Loading environment variables from {env_file}")
else:
    if __name__ == "__main__": print("No environment file specified. Loading environment variables from .env")
    env_file = '.env'
if slack_log_channel is not None:
    if __name__ == "__main__": print(f"Logging slack messages to {slack_log_channel}")
else:
    if __name__ == "__main__": print("No slack log channel specified. Not logging errors to slack")
    slack_log_channel = None

def clear_env_vars(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                key = line.split("=",  1)[0].strip()
                if key in os.environ:
                    del os.environ[key]
env_path = Path('.') / env_file
clear_env_vars(env_path)
load_dotenv(dotenv_path=env_path)

metadata_defaults = {
        'model_name': 'gpt-3.5-turbo',
        'temperature': 0,
        'completions': 1,
        'scoring_prompt': None,
        'reasoning_before_answer': True,
        'use_only_prompt': False,
        'steps_as_context': [],
        'debug': False
    }

metadata_forced_defaults = {
    'reasoning_before_answer': False,
    'use_only_prompt': True,
    'steps_as_context': None,  # when None, assume all earlier steps are in the context
}

# import text_completion_engine as tce
import slack_block_generator as block_generator
import slack_custom_actions as ssb
import openrouter_engine as ore
import promptchain as pc
import promptchain_parser as pcp
import edword as ed
# import subjectline_tools as slt
from server_utils import (
    construct_combined_message, trim_content,
    download_and_unzip_folder, download_file_content,
    save_promptfolder_to_redis,
    get_file_info,
    form2init_values_list,
    get_template_selections,
    # get_end_folder,
    zip_folder,
    generate_csv_file,
    job_started_message,
    job_end_message, prompt_queue_monitor_message,
    send_csv_articles,
    send_prompt_folder, set_promptfolder_button, send_button,
    filled_prompt_to_file, string_to_slack, build_form_v2,
    post_article, post_article_txt, insert_after, split_text,
    setup_logging, cycle_loading_reaction_emojis,
    get_convo_id, 
    get_user_prompts_folder,
    diff_emails, get_edited_email,
    stack_trace_message,
    save_to_temp_folder,
    print_directory_tree,
    validate_init_values,
    get_user_init_values, build_new_default_template_path, 
    build_form, send_form, update_form, folder_to_dict, ensure_view_size,
    thread_bot_responder, 
)
import article_writer
import linecache
import queue

#from ruamel.yaml import YAML
#import ruamel.yaml.representer

# def str_presenter(dumper, data):
#     if len(data.splitlines()) > 1:  # check for multiline string
#         return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
#     return ruamel.yaml.representer.SafeRepresenter.represent_str(dumper, data)

# yaml = YAML()
# yaml.Representer.add_representer(str, str_presenter)


class SlackLoggingHandler(logging.Handler):
    def __init__(self, slack_actions, log_queue, level):
        super().__init__()
        self.slack_actions = slack_actions
        self.setLevel(level)
        self.log_queue = log_queue

    def emit(self, record, pr=False):
        if pr: print("Emit method called")
        log_entry = self.format(record)
        if pr: print(f"Received log entry: {log_entry}")
        full_traceback = ''
        prev_5lines = ''
        project_traceback = ''
        if pr: print(f"record.exc_info: {record.exc_info}")
        if record.exc_info:
            full_traceback = ''.join(traceback.format_exception(*record.exc_info))
            tb_path = os.path.dirname(os.path.abspath(__file__))
            lines = full_traceback.split('\n')
            for i in range(len(lines)):
                if tb_path in lines[i]:  
                    # Get the previous 5 lines
                    split_line = lines[i].split('File ')[1].split(', line ')
                    split_line[1] = split_line[1].split(",")[0]
                    if len(split_line) >= 2:
                        file_path = split_line[0].replace('"', '')
                        line_number_str = split_line[1]
                        if line_number_str.isdigit():
                            line_number = int(line_number_str)
                            for j in range(line_number-1, line_number-6, -1):
                                if j > 0:  
                                    prev_5lines = linecache.getline(file_path, j) + prev_5lines

                    # Get the project traceback
                    project_traceback = '\n'.join(lines[i:])

            log_entry = f"{log_entry}\n\nprev_5lines:\n{prev_5lines}"
            self.log_queue.put(log_entry)

app = AsyncApp(token=os.environ["SLACK_TOKEN"])
# from slack_bolt.adapter.socket_mode import SocketModeHandler
# handler = SocketModeHandler(app, os.environ["WEBSOCKET_TOKEN"])
# Assuming you have an instance of AsyncApp called app
slack_custom_actions_toolbox = ssb.SlackCustomActions(app, None, None, how_to_guide='', logging_channel=slack_log_channel, pr=False)
handler = SlackLoggingHandler(slack_custom_actions_toolbox, queue.Queue(), logging.INFO)  # (slack_log_channel, os.environ["SLACK_TOKEN"])
slack_custom_actions_toolbox.message_handler = handler
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# call openrouter to get the latest version of the models
openrouter_engine = ore.OpenrouterEngine(checkup=False)
prompt_chain = pc.PromptChain(pr=True)
md_structure_info = pcp.md_input
handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.addHandler(handler)
root_logger.setLevel(logging.INFO)
logger = app.logger
# logger.setLevel(logging.DEBUG)


# Log a message at the DEBUG level
logger.debug("This is a debug message")

processed_events = set()

# Check the size of the queue
# print("Queue size:", slack_custom_actions_toolbox.message_handler.log_queue.qsize())

# logger.debug("Test debug message")
# logger.info("Test info message")
# logger.warning("Test warning message")
# logger.error("Test error message")
# logger.critical("Test critical message")

# # Now you can use your logger as before
# try:
#     1 / 0  # This will raise a ZeroDivisionError
# except Exception as e:
#     logger.exception('An error occurred')
# print("Queue size:", slack_custom_actions_toolbox.message_handler.log_queue.qsize())
# async def main():
#     await slack_custom_actions_toolbox.send_log_messages()

# if __name__ == "__main__":
#     asyncio.run(main())
# exit()

if __name__ == "__main__": print(redis_host)
if redis_host:
    if __name__ == "__main__": print("Connecting to redis host")
    redis_client = redis.Redis(host='redis', port=6379, db=0)
else:
    if __name__ == "__main__": print("Connecting to local redis")
    redis_client = redis.Redis(host='localhost', port=6379, db=0)

# global variables
job_info = {}
monitor_channels = ["pytesting"]
if channel:
    monitor_channels = [channel]
# import code; code.interact(local=dict(globals(), **locals()))
monitor_channel_id = get_convo_id(monitor_channels[0], pr=False)
# init_values = ["Pipe_Hitter_Foundation", "fundraising", "Extra instructions go here", True, False, "gpt-3.5-turbo", "0.5", "3"]
# possible future alternative to initial_values. Gonna have to live with magic list labels for now
# init_values = { # block_types are limited to input, input-multiline, select, checkbox
#             "Use_template": {"value": True, "form_search_key": "selected_options", "block_type": "checkbox"}, 
#             "client": {"value": "Pipe_Hitter_Foundation", "form_search_key": "selected_option/text/text", "block_type": "select-folder"}, 
#             "email": {"value": "fundraising", "form_search_key": "selected_option/text/text", "block_type": "select-folder"},
#             # "prompt_quickeditor": {"value": True, "form_search_key": "selected_options", "block_type": "checkbox"},
#             "writing_instructions": {"value": "Extra instructions go here", "form_search_key": "value", "block_type": "input-multiline"},
#             "model": {"value": "gpt-3.5-turbo", "form_search_key": "selected_option/text/text", "block_type": "select"},
#             "temperature": {"value": "0.5", "form_search_key": "value", "block_type": "input"}, 
#             "samples": {"value": "3", "form_search_key": "value", "block_type": "input"},
#         }

md_promptchain = """## Variables
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
- model: openai/gpt-3.5-turbo  ## example bestest model for subject lines
- temperature: 1
- completions: 1
- scoring_prompt: 

### Copywriter character persona
Ideate the ideal copywriter character persona. Someone hardworking, creative, and worldly.
- temperature: 1
- completions: 3

### select the best writer
[[copywriter_character_persona.all]]

Choose the best writer from the above list of writers
"""


default_prompt = "What color is the sky?"
default_prompt = f"Write fundraising email copy for TPUSA"

default_template_path = "templates/newsletter/Pipe_Hitter_Foundation/fundraising"
# default_template_path = "templates/pirate_speak"
default_folder_path = "./templates"
inits_on_first_start = True
# default_template_path = "templates/pirate_speak"
button_values = ["new", "view_prompt", "delete", "rename"]  # , "info"]
template_button_values = ["new_client"] + button_values[1:]
button_id_ends = ["_button_create_new", "_button_prompt", "_button_delete", "_button_rename"]  # , "_button_info"]
folder_choices = ["template", "folder_1", "folder_2", "variables"]
def create_end_ids_for_each_choice(choices, id_ends):
    variables = {}
    for choice in choices:
        variables[choice] = [choice + id_end for id_end in id_ends]
    return variables
folder_buttons = create_end_ids_for_each_choice(folder_choices, button_id_ends)
# function that creates a button ids list
def create_button_ids(front, button_id_ends):
    return [front + end for end in button_id_ends]
# a tuple that holds everything nessisary to create arbitrary buttons. Include create_button_ids
button_states = (button_values, button_id_ends, create_button_ids)
init_values = { # block_types are limited to input, input-multiline, select, checkbox
        "sf_template_name_id": {"block_text": "Job Name", "visable": True, "value": "AVC Oct 2023 F3", "form_search_key": "value", "block_type": "input", "action_id": "job_name"},
        "Edit_templates": {"block_text": "Edit", "visable": False, "value": False, "form_search_key": "selected_options", "block_type": "checkbox", "action_id": "Edit_templates"}, 
        
        "template": {"block_text": "client", "level": 0, "visable": False, "value": "Faith_and_Freedom", "form_search_key": "selected_option/text/text", "block_type": "select-folder", "action_id": "template"}, 
        "template_buttons": {"block_text": " ", "level": 0, "visable": False, "value": template_button_values, "form_search_key": "selected_options", "block_type": "button", "action_id": folder_buttons["template"]},
        "template_info": {"block_text": " ", "level": 0, "visable": False, "value": " ", "form_search_key": "selected_option/text/text", "block_type": "text", "action_id": None}, 
        "template_rename": {"block_text": "rename", "level": 0, "visable": False, "value": "template_rename", "form_search_key": "value", "block_type": "input", "action_id": "template_rename"}, 
        "new_template_name": {"block_text": "new client's name", "level": 0, "visable": False, "value": " ", "form_search_key": "value", "block_type": "input", "action_id": "new_template_name"}, 
        "start/copy_from_template": {"block_text": "* _*optional*_ * - start with a copy of", "level": 0, "visable": False, "value": "None", "form_search_key": "selected_option/text/text", "block_type": "select-folder", "action_id": "start/copy_from_template"}, 
        "template_prompt": {"block_text": "prompt", "level": 0, "visable": False, "value": "core prompt goes here", "form_search_key": "value", "block_type": "input-multiline", "action_id": "template_prompt"},
        "template_save_button": {"block_text": "Save changes", "level": 0, "visable": False, "value": "Save_changes", "form_search_key": "selected_options", "block_type": "button", "action_id": "template_button_Save_changes"},

        "folder_1": {"block_text": "email type", "level": 1, "visable": False, "value": "aquisition", "form_search_key": "selected_option/text/text", "block_type": "select-folder", "action_id": "folder_1"},
        "folder_1_buttons": {"block_text": " ", "level": 1, "visable": False, "value": button_values, "form_search_key": "selected_options", "block_type": "button", "action_id": folder_buttons["folder_1"]},
        "folder_1_info": {"block_text": " ", "level": 1, "visable": False, "value": " ", "form_search_key": "selected_option/text/text", "block_type": "text", "action_id": None},
        "folder_1_rename": {"block_text": "rename", "level": 1, "visable": False, "value": "folder_1_rename", "form_search_key": "value", "block_type": "input", "action_id": "folder_1_rename"},
        "new_folder_1_name": {"block_text": "new email type's name", "level": 1, "visable": False, "value": " ", "form_search_key": "value", "block_type": "input", "action_id": "new_folder_1_name"},
        "start/copy_from_folder_1": {"block_text": "* _*optional*_ * - start with a copy of", "level": 1, "visable": False, "value": "None", "form_search_key": "selected_option/text/text", "block_type": "select-folder", "action_id": "start/copy_from_folder_1"},
        "folder_1_prompt": {"block_text": "prompt", "level": 1, "visable": False, "value": "core prompt goes here", "form_search_key": "value", "block_type": "input-multiline", "action_id": "folder_1_prompt"},
        "folder_1_save_button": {"block_text": "Save changes", "level": 1, "visable": False, "value": "Save_changes", "form_search_key": "selected_options", "block_type": "button", "action_id": "folder_1_button_Save_changes"},

        "folder_2": {"block_text": "email template", "level": 2, "visable": False, "value": "fundraising", "form_search_key": "selected_option/text/text", "block_type": "select-folder", "action_id": "folder_2"},
        "folder_2_buttons": {"block_text": " ", "level": 2, "visable": False, "value": button_values, "form_search_key": "selected_options", "block_type": "button", "action_id": folder_buttons["folder_2"]},
        "folder_2_info": {"block_text": " ", "level": 2, "visable": False, "value": " ", "form_search_key": "selected_option/text/text", "block_type": "text", "action_id": None},
        "folder_2_rename": {"block_text": "rename", "level": 2, "visable": False, "value": "folder_2_rename", "form_search_key": "value", "block_type": "input", "action_id": "folder_2_rename"},
        "new_folder_2_name": {"block_text": "new email template's name", "level": 2, "visable": False, "value": " ", "form_search_key": "value", "block_type": "input", "action_id": "new_folder_2_name"},
        "start/copy_from_folder_2": {"block_text": "* _*optional*_ * - start with a copy of", "level": 2, "visable": False, "value": "None", "form_search_key": "selected_option/text/text", "block_type": "select-folder", "action_id": "start/copy_from_folder_2"},
        "folder_2_prompt": {"block_text": "prompt", "level": 2, "visable": False, "value": "core prompt goes here", "form_search_key": "value", "block_type": "input-multiline", "action_id": "folder_2_prompt"},
        "folder_2_save_button": {"block_text": "Save changes", "level": 2, "visable": False, "value": "Save_changes", "form_search_key": "selected_options", "block_type": "button", "action_id": "folder_2_button_Save_changes"},

        "variables": {"block_text": "variables", "level": 1, "visable": False, "value": "var_rental", "form_search_key": "selected_option/text/text", "block_type": "select-folder", "action_id": "variables"},
        "variables_buttons": {"block_text": " ", "level": 1, "visable": False, "value": button_values, "form_search_key": "selected_options", "block_type": "button", "action_id": folder_buttons["variables"]},
        "variables_info": {"block_text": " ", "level": 1, "visable": False, "value": " ", "form_search_key": "selected_option/text/text", "block_type": "text", "action_id": None},
        "variables_rename": {"block_text": "rename", "level": 1, "visable": False, "value": "variables_rename", "form_search_key": "value", "block_type": "input", "action_id": "variables_rename"},
        "new_variables_name": {"block_text": "new variable's name", "level": 1, "visable": False, "value": " ", "form_search_key": "value", "block_type": "input", "action_id": "new_variables_name"},
        "variables_prompt": {"block_text": "prompt", "level": 1, "visable": False, "value": "core prompt goes here", "form_search_key": "value", "block_type": "input-multiline", "action_id": "variables_prompt"},
        "variables_save_button": {"block_text": "Save changes", "level": 1, "visable": False, "value": "Save_changes", "form_search_key": "selected_options", "block_type": "button", "action_id": "variables_button_Save_changes"},

        "prompt_queue_checkbox": {"block_text": "PromptChaining - New Markdown Format!!", "visable": True, "value": False, "form_search_key": "selected_options", "block_type": "checkbox", "action_id": "prompt_queue_checkbox"}, 

        "writing_instructions": {"block_text": "Prompt", "visable": True, "value": "What color is the sky?", "form_search_key": "value", "block_type": "input-multiline", "action_id": "writing_instructions"},        
        "preview_checkbox": {"block_text": "preview prompt", "visable": False, "value": False, "form_search_key": "selected_options", "block_type": "checkbox", "action_id": "preview_checkbox"},
        "preview": {"block_text": "prompt preview", "visable": False, "value": " ", "form_search_key": "selected_option/text/text", "block_type": "text", "action_id": "preview_0"},
        "temperature": {"block_text": "temperature", "visable": True, "value": "0.75", "form_search_key": "value", "block_type": "input", "action_id": "temperature"}, 
        "samples": {"block_text": "completions", "visable": True, "value": "2", "form_search_key": "value", "block_type": "input", "action_id": "samples"},
        "model": {"block_text": "model", "visable": True, "value": "anthropic/claude-3-haiku", "form_search_key": "selected_option/text/text", "block_type": "select", "action_id": "model"},
    }
"openai/gpt-4-0314"
"openai/gpt-3.5-turbo-0613"
rewrite_preset_prompt = f"Please rewrite the following email to align closer with the above client values and email format:\n\n"
# Initialize a WebClient using the app's Slack token
client = AsyncWebClient(token=os.environ["SLACK_TOKEN"])

# Load the base modal form's content from the JSON file
with open("slack_block_template.json", "r") as file:
    modal_content = json.load(file)

# load base message blocks from json file
with open("slack_form_entry_message_blocks.json", "r") as file:
    message_blocks = [json.load(file)]

# Function to send a message with a button to trigger the modal form
async def send_form_trigger_message(channel_id):
    try:
        # Send the message to the channel
        response = await app.client.chat_postMessage(
            channel=channel_id,
            text="", # Add a text argument here
            blocks=message_blocks
        )
    except SlackApiError as e:
        logger.exception(f"Error sending form trigger message:")
    return response

async def cycle_loading_emojis(job_id, channel_id):
    emojis = [":hourglass:", ":hourglass_flowing_sand:"]
    index = 0
    starting_rate = 0.5
    rate_limit_wait_time = 1 # time to wait before slowing down the rate
    slower_rate = 5
    while not job_info.get(job_id, {}).get('completed', True):
        if index*starting_rate > rate_limit_wait_time:
            await asyncio.sleep(slower_rate)
        else:
            await asyncio.sleep(starting_rate)
        emoji = emojis[index % len(emojis)]
        if job_id in job_info:
            core_response_ts = job_info[job_id]['core_response_ts']
            original_message = job_info[job_id]['original_message']
            if core_response_ts is not None:
                new_message = original_message.replace(":hourglass:", emoji).replace(":hourglass_flowing_sand:", emoji)
                try:
                    channel = channel_id
                    await app.client.chat_update(
                        channel=channel,
                        ts=core_response_ts,
                        text=new_message,
                    )
                except SlackApiError as e:
                    logger.exception(f"Error updating message with emoji:")
        index += 1

@app.action("set_promptfolder")
async def handle_some_action(ack, body, logger):
    await ack()
    logger.info(body)
    channel_id = body['channel']['id']
    user_id = body['user']['id']
    if body.get('container', None) is None:
        return
    is_thread = False 
    if 'thread_ts' in body.get('container', None):
        is_thread = True
    global default_folder_path, redis_client, slack_custom_actions_toolbox
    if user_id == slack_custom_actions_toolbox.bot_id or channel_id != monitor_channel_id:
        return
    
    if is_thread:
        event_id = body['container'].get('thread_ts', None)
    else:
        event_id = body['container'].get('message_ts', None)
    if event_id in processed_events and event_id is not None:
        # This event has already been processed, so ignore it
        return
    # Add the event ID to the set of processed events
    processed_events.add(event_id)
    try:
        if is_thread:
            thread_ts = body['message']['thread_ts']
            thread_response = await app.client.conversations_replies(channel=channel_id, ts=thread_ts)
            messages = thread_response['messages']
            folder_message = messages[2]
            file_id = folder_message['files'][0]['id']
        else:
            # get the file id from the message right before this one and save it to redis
            history_response = await app.client.conversations_history(
                channel=channel_id,
                latest=body['container']['message_ts'],  # Stop at the set_promptfolder message
                inclusive=False  # Don't include the set_promptfolder message itself
                )
            messages = history_response['messages']
            # Filter out ephemeral messages
            non_ephemeral_messages = [message for message in messages if 'subtype' not in message or message['subtype'] != 'bot_message']
            # Reverse the list of non-ephemeral messages
            non_ephemeral_messages.reverse()
            if non_ephemeral_messages:
                # The previous message is now the last one in the list, because we reversed it
                previous_message = non_ephemeral_messages[-1]
            else:
                logger.warn("No previous message found")
            file_id = previous_message['files'][0]['id']
        file_info = await get_file_info(file_id, os.environ["SLACK_TOKEN"])
        file_name = file_info["file"]["name"]
        temp_dir = get_user_prompts_folder(user_id, redis_client, default_folder_path, logger, False)
        await save_promptfolder_to_redis(app.client, channel_id, file_id, file_name, user_id, redis_client, os.environ["SLACK_TOKEN"], logger)
        await send_prompt_folder(app.client, temp_dir, user_id, channel_id, None, logger, init_cmt="\'s old Templates", msg=f" ")  # <@{user_id}>'s old promptfolder

            
    except SlackApiError as e:
        await stack_trace_message(app.client, user_id, channel_id, folder_message['ts'], e, logger)
        logger.exception(f"Error generating articles for {user_id}:")

@app.event("file_shared")
async def handle_file_shared(ack, body, logger):
    await ack()
    # print(body)
    channel_id = body["event"]["channel_id"]
    user_id = body["event"]["user_id"]
    if channel_id != monitor_channel_id or user_id == slack_custom_actions_toolbox.bot_id:
        return
    # Get file ID and file name
    file_id = body["event"]["file_id"]
    file_info = await get_file_info(file_id, os.environ["SLACK_TOKEN"]) 
    file_name = file_info["file"]["name"]
    # exit if the file is not a zip file
    if not file_name.endswith(".zip"):
        return

    logger.info("Received a file_shared event", extra={"file_id": file_id, "file_name": file_name})
    # get the user's old prompt folder
    global default_folder_path, redis_client
    temp_dir = get_user_prompts_folder(user_id, redis_client, default_folder_path, logger, False)
    await save_promptfolder_to_redis(app.client, channel_id, file_id, file_name, user_id, redis_client, os.environ["SLACK_TOKEN"], logger)
    await set_promptfolder_button(app.client, channel_id, None, msg=" ")  # to allow other user's access to the newly uploaded prompt folder
    await send_prompt_folder(app.client, temp_dir, user_id, channel_id, None, logger, init_cmt="\'s old Templates", msg=f" ")  # <@{user_id}>'s old promptfolder

async def process_form_submission(form_type, ack, body, view, logger, queue_edit=None):
    global job_info, init_values, default_folder_path, inits_on_first_start, redis_client, button_states, openrouter_engine, prompt_chain, slack_custom_actions_toolbox, md_structure_info

    queue_edit = queue_edit
    submitted_data = view["state"]["values"]
    user_id = body["user"]["id"]
    dict_init_values = init_values
    start_time = time.time()
    piece_name = dict_init_values['sf_template_name_id']['value']
    # import code; code.interact(local=dict(globals(), **locals()))
    if not queue_edit:
        piece_name = submitted_data[list(submitted_data.keys())[0]]['sf_template_name_id']['value']
        user_init_values = await get_user_init_values(user_id, init_values, redis_client, inits_on_first_start)
        # get user folder from redis, then get the folder path. Otherwise, use the default folder path 
        temp_dir = get_user_prompts_folder(user_id, redis_client, default_folder_path, logger, inits_on_first_start)
        # print(temp_dir)

        # Convert the submitted_data to init_values
        dict_init_values = form2init_values_list(submitted_data, user_init_values, temp_dir, button_states)
        # print(json.dumps(dict_init_values, indent=4))
        # logger.info(dict_init_values)
        result = await validate_init_values(app.client, dict_init_values, user_id, monitor_channels, logger)
        if result[0] is False:  # exit function
            return
        temperature = result[1]
        completions = result[2]

        # Store the dict_init_values in Redis for the user
        if not dict_init_values["prompt_queue_checkbox"]["value"]:
            dict_init_values['sf_template_name_id']['value'] = ""  # reset the sf_template_name_id. This forces user to name their piece something (hopefully) unique
        
        writing_instructions = dict_init_values['writing_instructions']['value']
        dict_init_values['writing_instructions']['value'] = ""
        redis_client.set(f"{user_id}_job_form", json.dumps(dict_init_values))
        dict_init_values['writing_instructions']['value'] = writing_instructions
        
        template_selections = None
        if dict_init_values["template"]["value"] != "None":
            template_selections = get_template_selections(view, dict_init_values, default_folder_path, button_states)
    else:
        dict_init_values['prompt_queue_checkbox']['value'] = True # this is a hack to get the prompt_queue_checkbox to be True
        # create dummy core_response object. core_response must have a .data attribute and be a dict
        class CoreResponse:
            def __init__(self):
                self.data = {}

            def __getitem__(self, key):
                return getattr(self, key)

            def __setitem__(self, key, value):
                setattr(self, key, value)

        core_response = CoreResponse()
        core_response.data['channel'] = monitor_channel_id
        core_response['ts'] = str(redis_client.get(f"{user_id}_thread_ts"))
    
    # interpret markdown2basicPromptQueueFormat 
    # def markdown2PromptQueueFormat(markdown):
    
    if dict_init_values["prompt_queue_checkbox"]["value"] is True:
        start_time = time.time()
        job_id = f"{user_id}_{start_time}"
        try:
            if queue_edit:
                # queue_edit = {
                #     "step": step,
                #     "variables_up_to_this_step": variables_up_to_this_step,
                #     "new_promptsteps": new_promptsteps,
                #     "old_promptsteps": old_promptsteps_,
                #     # thread_ts is the thread_ts of the button press
                #     "thread_ts": redis_client.get(f"{user_id}_thread_ts"),
                #     # increment the prompt_queue by just and only one step
                #     "increment_prompt_queue": submitted_data["increment_prompt_queue"]["increment_prompt_queue"]["selected_option"]['value'] == "value-0"
                # }
                # from queue_edit combine variables_up_to_this_step and new_promptsteps and feed into get_md
                if queue_edit['increment_prompt_queue']:
                    if len(queue_edit['new_promptsteps']) > 1:
                        queue_edit['not_executable_promptsteps'] = queue_edit['new_promptsteps'][1:]
                    queue_edit['new_promptsteps'] = [queue_edit['new_promptsteps'][0]]
                try:                
                    writing_instructions = prompt_chain.get_md(queue_edit['variables_up_to_this_step'], queue_edit['new_promptsteps'])
                except Exception as e:
                    print(e.with_traceback())
                    # print much more info
                    # import code; code.interact(local=dict(globals(), **locals()))
                step = queue_edit['step']
            else:
                step = 1
            # for api stability, ascii encode and decode to remove any non-ascii characters
            writing_instructions = writing_instructions.encode('ascii', 'ignore').decode('ascii')
            # test the writing_instructions to see if it's valid promptchain md format
            try:
                parsed_chain = prompt_chain.md_promptchain_parser(writing_instructions, models=openrouter_engine.models)
            except Exception as e:
                # print(json.dumps(dict_init_values, indent=4))
                
                # view['state']['values'][list(view['state']['values'].keys())[-1]]
                # errors = {"errors": {"writing_instructions": "There is a yaml error in the prompt. Please fix the error and try again.\n\n" + str(e)}}
                # await ack(response_action="errors", errors=errors)

                # quickly alert the user to the error and tell them to wait for the error message suggestion
                first_error_dict = {"error": {
                                "block_text": "md Formatting Error",
                                "visable": True,
                                "value": f"There is a formatting error in the promptchain markdown. Please wait a moment for Savant to suggest a fix.",
                                "form_search_key": "selected_option/text/text",
                                "block_type": "text",
                                "action_id": "error_0"
                            }}
                dict_init_values_copy__ = copy.deepcopy(dict_init_values)
                dict_init_values_ = insert_after(dict_init_values_copy__, "writing_instructions", first_error_dict)
                new_view = await build_form_v2(dict_init_values_, debug=True)
                old_view = view

                wait_form_response = await update_form(app.client, body, old_view, json.dumps(new_view), logger)
                # import code; code.interact(local=dict(globals(), **locals()))
                await ack()
                
                # have an llm suggest a fix
                fix_prompt = f"{md_structure_info}\n\n\n\nFind and fix the following md formatting error found in the below md file:\n\nFile:\n{{writing_instructions}}\n\n\nError:\n\n{e}\n\nBe very concise with the fix. DO NOT PRINT OUT THE ENTIRE FILE. Explain the fix in 2 sentences(MAX) like I'm 5."
                fix_task = await openrouter_engine.acomplete(fix_prompt, model="openai/gpt-4o", max_tokens=70, temperature=0.20, completions=1)
                fix = fix_task["completions"][0]
                error_msg = f"md Formatting Error: {e}\n\n\nSuggested Fix: {fix}"
                if len(error_msg) > 3000:  # 3000 is the max length of a block_text in slack
                    error_msg = error_msg[:2997] + "..."
                error_dict = {"error": {
                                "block_text": "md Formatting Error",
                                "visable": True,
                                "value": error_msg,
                                "form_search_key": "selected_option/text/text",
                                "block_type": "text",
                                "action_id": "error_0"
                            }}
                # insert error_dict just after writing_instructions in dict_init_values
                dict_init_values = insert_after(dict_init_values, "writing_instructions", error_dict)
                new_view = await build_form_v2(dict_init_values)
                try:
                    # wait_form_response_2 = await update_form(app.client, body, wait_form_response.data['view'], json.dumps(new_view), logger)
                    send_form_response = await send_form(app.client, body, new_view, logger)
                except Exception as e:
                    print(e)
                    # import code; code.interact(local=dict(globals(), **locals()))

                redis_client.set(f"{user_id}_job_form", json.dumps(dict_init_values))
                return
            await ack()
            if queue_edit:
                starter_variables = queue_edit['starter_variables']

                # show that we're working on stuff
                job_info[job_id] = {"completed": False, "core_response_ts": core_response['ts'], "original_message": None}
                loading_task = asyncio.create_task(cycle_loading_reaction_emojis(job_id, job_info, monitor_channel_id, app.client, logger))
            else:
                starter_variables = parsed_chain["variables"]
                core_response, job_id, job_id_metadata = await job_started_message(app.client, user_id, monitor_channels, dict_init_values, logger)
                running_cost = 0
                text_to_show = f"""sf_template_name_id: {piece_name}\nuser: <@{user_id}>\njob_type: prompt_queue\nstep: 0/{len(parsed_chain['promptchain'])}\nruntime: {str(round(time.time()-start_time, 2))}\ncost_dollars: {str(round(running_cost, 6))}"""
                await prompt_queue_monitor_message(app.client, core_response, text_to_show)
                job_info[job_id] = job_id_metadata
                loading_task = asyncio.create_task(cycle_loading_reaction_emojis(job_id, job_info, monitor_channel_id, app.client, logger))
                # send the writing_instructions prompt to the thread
                await filled_prompt_to_file(app.client, writing_instructions, core_response, {}, logger, initial_comment=" ", file_name="promptchain.md")
            # if queue_edit:
            #     # place here to auto update prompt summaries
            #     prompt_queue = queue_edit['prompt_queue_up_to_step']
            ts = float(time.time())
            # parsed_chain passed validation
            prompt_chain_task = asyncio.create_task(prompt_chain.run_chain(writing_instructions, job_id=ts))

            async def print_as_steps_complete(prompt_chain_task, job_id, running_cost=0, start_time=start_time, core_response=core_response, idx=step):
                # wait until prompt_chain.step_progress_queues[job_id]["print_ready_queue"] exists
                max_iter = 1000
                while job_id not in prompt_chain.step_progress_queues.keys():
                    print(f"waiting for {job_id} in prompt_chain.step_progress_queues\nprompt_chain.step_progress_queues.keys(): {prompt_chain.step_progress_queues.keys()}")
                    await asyncio.sleep(0.1)
                    print("waiting for prompt_chain.step_progress_queues")
                    if max_iter == 0:
                        raise Exception("max_iter reached")
                    max_iter -= 1
                if queue_edit:
                    # self.step_progress_queues[list(self.step_progress_queues.keys())[0]]["print_ready_queue"]
                    # set the promptsteps to the old promptsteps
                    prompt_chain.step_progress_queues[job_id]["promptsteps"] = queue_edit['old_promptsteps'] + queue_edit['new_promptsteps']
                past_prompt_steps_list = []; aggregated_vars = {}
                errors = []
                while len(prompt_chain.step_progress_queues[job_id]["print_ready_queue"]) > 0 or not prompt_chain_task.done():
                    await asyncio.sleep(0.1)
                    if len(prompt_chain.step_progress_queues[job_id]["print_ready_queue"]) > 0:
                        # pop the first element in the print_ready_queue and print it
                        prompt_queue_el = prompt_chain.step_progress_queues[job_id]["print_ready_queue"].pop(0)
                        past_prompt_steps_list.append(prompt_queue_el['promptstep'])
                        # aggregate the variables
                        aggregated_vars.update(prompt_queue_el['variables'])
                        # print the prompt_queue_el
                        print(prompt_queue_el)
                        button_text = f"Edit PromptStep {idx}"
                        button_msg_text = f"Prompt {idx}"  # f"{prompt_queue_el['promptstep']['name']}"  # \n{prompt_queue_el['promptstep']['unfilled_prompt']}"  # b/c unfilled_prompt is typically shorter than filled_prompt
                        await send_button(client, core_response, button_msg_text, button_text, "edit_step_button", logger)
                        # sum the cost of the promptstep
                        step_cost = float(prompt_queue_el['output']['cost_dollars'])
                        running_cost += step_cost
                        step_avg_cost = float(prompt_queue_el['output']['avg_cost'])
                        step_runtime = float(prompt_queue_el['output']['runtime'])
                        step_tokens_prompt = float(prompt_queue_el['output']['tokens_prompt'])
                        step_avg_tokens_completion = float(prompt_queue_el['output']['avg_tokens_completion'])
                        step_tokens_per_second = round(step_avg_tokens_completion / step_runtime, 6)

                        # turn into multiline string
                        stats = f"""step_cost: {step_cost}\nstep_avg_cost: {step_avg_cost}\nstep_runtime: {step_runtime}\nstep_tokens_prompt: {step_tokens_prompt}\nstep_avg_tokens_completion: {step_avg_tokens_completion}\nstep_tokens_per_second: {step_tokens_per_second}"""

                        # send the promptstep instructions + model metadata to a promptstep_n_state_file.md
                        if queue_edit:
                            print(len(prompt_chain.step_progress_queues[job_id]["promptsteps"]))
                            print(len(queue_edit['old_promptsteps']))
                            print(len(queue_edit['new_promptsteps']))
                            print("index", idx)
                            # import code; code.interact(local=dict(globals(), **locals()))
                        statefile_content = prompt_chain.generate_statefile(aggregated_vars, prompt_chain.step_progress_queues[job_id]["promptsteps"], idx-1, starter_variables, var_filled_prompt=prompt_queue_el['promptstep']['filled_prompt'], stats=stats)
                        response = await string_to_slack(app.client, statefile_content, core_response, logger, initial_comment=" ", file_name=f"promptstep_{idx}_statefile.md")
                        # if response:
                        #     pass
                        # import code; code.interact(local=dict(globals(), **locals()))
                        # import code; code.interact(local=dict(globals(), **locals()))
                        # for each completion in the prompt_queue_el, send the completion to the thread
                        # if the key "list_completions" is in the output, then append the contents of "list_completions" and "completion_errors" to the thread
                        promptchain_mapping = False
                        if 'list_completions' in prompt_queue_el['output'].keys():
                            promptchain_mapping = True
                            # append the list_completions and completion_errors to the thread
                            completions_ = prompt_queue_el['output']['list_completions'] + prompt_queue_el['output']['completion_errors']
                            prompt_queue_el['output']['completions'] = prompt_queue_el['output']['list_completions']
                            # if len(prompt_queue_el['output']['completion_errors']) == len(prompt_queue_el['output']['completions']):
                            #     # raise Exception("All completions are parsing errors")
                            #     await stack_trace_message(app.client, user_id, core_response.data['channel'], core_response["ts"], "All completions are parsing errors", logger)
                            #     logger.exception(f"Error generating articles for {user_id}:")
                            #     # end the job
                            #     job_info[job_id]['completed'] = True
                            #     try:
                            #         loading_task.cancel()
                            #     except:
                            #         pass
                            #     raise Exception("All completions are parsing errors")
                        else:
                            completions_ = prompt_queue_el['output']['completions']
                        print(completions_)
                        for i, completion in enumerate(completions_):
                            completion = str(completion)
                            if len(prompt_queue_el['output']['metadata']) >= i+1:
                                word_token_char_counts = f"words: {len(completion.split(' '))}\ttokens: {prompt_queue_el['output']['metadata'][i]['native_tokens_completion']}\tcharacters: {len(completion)}"
                            else:
                                word_token_char_counts = f" "
                            # send the completion to the thread
                            # import code; code.interact(local=dict(globals(), **locals()))
                            await string_to_slack(app.client, completion, core_response, logger, initial_comment=word_token_char_counts, file_name=f"promptstep_{idx}_completion_{i+1}.txt")
                            # if the docx key is in the step metadata and set to True, then convert the completion to a docx file. Else, send as a md file
                            if 'docx' in prompt_queue_el['promptstep'].keys() and prompt_queue_el['promptstep'].get('docx', False):
                                file_name = f"promptstep_{idx}_completion_{i+1}.docx"
                                docx_path = ed.Edword().md_to_docx(completion, file_name)
                                # file to slack
                                async def file_upload_to_slack(client, file_path, file_name, channel_id, initial_comment=""):
                                    try:
                                        response = await client.files_upload(
                                            channels=channel_id,
                                            initial_comment=initial_comment,
                                            file=file_path,
                                            thread_ts=core_response['ts'],
                                            title=file_name,
                                        )
                                    except SlackApiError as e:
                                        logger.exception(f"Error uploading file to slack:")
                                    return response
                                
                                await file_upload_to_slack(app.client, docx_path, file_name, core_response.data['channel'], initial_comment=" ")
                            await asyncio.sleep(0.1)


                        text_to_show = f"""sf_template_name_id: {piece_name}\nuser: <@{user_id}>\njob_type: prompt_queue\nstep: {idx}/{len(prompt_chain.step_progress_queues[job_id]["promptsteps"])}\nruntime: {str(round(time.time()-start_time, 2))}\ncost_dollars: {str(round(running_cost, 6))}"""

                        await prompt_queue_monitor_message(app.client, core_response, text_to_show)
                        # increment the idx
                        idx += 1
                    # except Exception as e:
                    #     # # send a stack trace message to the user through slack
                    #     # await stack_trace_message(app.client, user_id, core_response.data['channel'], core_response["ts"], e, logger)
                    #     # raise Exception(e)
                    #     # catch any errors and append them to the errors list
                    #     # this gives some time to send messages to slack before the error is raised. So that the user can see the error message at the correct location
                    #     errors.append(e)
                    #     print(e)
                    #     # import code; code.interact(local=dict(globals(), **locals()))
                    # dump error_queue from prompt_chain to slack
                    try:
                        error_queue = prompt_chain.step_progress_queues[job_id]["error_queue"][idx-1]
                    except:
                        error_queue = []
                    if len(error_queue) > 0:
                        error_str = ""
                        for i, error in enumerate(error_queue):
                            error_str += f"Error {i+1}: {error}\n\n"
                        await stack_trace_message(app.client, user_id, core_response.data['channel'], core_response["ts"], error_str, logger)
                    

                # # raise an error if there are any errors
                # if len(errors) > 0:
                #     # raise a giant error combining all the errors
                #     error_str = ""
                #     for i, error in enumerate(errors):
                #         # traceback for this specific error e
                #         error_str += f"Error {i+1}: {error.__traceback__}\n\n"
                #     # send the error to slack
                #     await stack_trace_message(app.client, user_id, core_response.data['channel'], core_response["ts"], error_str, logger)
                #     raise Exception(error_str)

                # for reproducability, print a md file of the promptchain + starter variables (not just a redundant promptchain.md file b/c this one could be a result of a queue_edit)
                end_promptsteps = []
                if queue_edit and len(queue_edit['new_promptsteps']) > 1:
                    end_promptsteps = queue_edit['not_executable_promptsteps']
                promptsteps = prompt_chain.step_progress_queues[job_id]["promptsteps"] + end_promptsteps
                reproducable_md = prompt_chain.get_md(starter_variables, promptsteps)
                # try to parse the md file to see if it's valid (it should always be valid)
                try:
                    parsed_chain = prompt_chain.md_promptchain_parser(reproducable_md, models=openrouter_engine.models)
                except Exception as e:
                    raise Exception(f"Error parsing the reproducable_md: {e}")
                await string_to_slack(app.client, reproducable_md, core_response, logger, initial_comment=" ", file_name=f"reproducible_promptchain.md")
                return

            # print the prompt_queue as steps complete
            prompt_queue_w_step_results = await print_as_steps_complete(prompt_chain_task, ts)
            prompt_queue = await prompt_chain_task
            
            job_info[job_id]['completed'] = True
        # for any error, send a stack trace message to the user through slack
        except Exception as e:
            await stack_trace_message(app.client, user_id, core_response.data['channel'], core_response["ts"], e, logger)
            logger.exception(f"Error generating articles for {user_id}:")
            # end the job
            job_info[job_id]['completed'] = True
            try:
                loading_task.cancel()
            except:
                pass
    else:
        await ack()
        core_response, job_id, job_id_metadata = await job_started_message(app.client, user_id, monitor_channels, dict_init_values, logger)
        job_info[job_id] = job_id_metadata
        loading_task = asyncio.create_task(cycle_loading_emojis(job_id, core_response.data['channel']))

        prompt = str(dict_init_values["writing_instructions"]["value"])
        # prompt_variables = {"email_examples": "", "writing_instructions": dict_init_values["writing_instructions"]["value"]}
        # # if the token len of writing_instructions is too long, then trim it
        # token_percent = 0.75
        # if dict_init_values["template"]["value"] == "None":
        #     token_percent = 1
        # max_token_len = int(tce.TextCompletionEngine(model_name=dict_init_values["model"]["value"]).context_len()*token_percent)
        # if tok_len(prompt_variables["writing_instructions"]) > max_token_len:
        #     prompt_variables["writing_instructions"] = tce.TextCompletionEngine(model_name=dict_init_values["model"]["value"]).keep_last_n(prompt_variables["writing_instructions"], max_token_len)
        try:
            # Generate the articles
            # aw = article_writer.ArticleWriter(model_name=dict_init_values["model"]["value"], temp=temperature)
            # output = await aw.write_email(temp_dir, template_selections, prompt_variables=prompt_variables, model_dict=dict_init_values, completions=completions) 
            engine = ore.OpenrouterEngine(checkup=False)
            engine.models = openrouter_engine.models
            # print(json.dumps(dict_init_values, indent=4))

            output = await engine.acomplete(prompt, completions=int(dict_init_values["samples"]["value"]), model=dict_init_values["model"]["value"], temperature=float(dict_init_values["temperature"]["value"]))
            articles = output["completions"]
            #prompt = output["prompt"]
            # metadata is a dictionary of all the keys and values passed the metadata key in output
            # get all the keys and values after the metadata key
            metadata = {k: v for k, v in output.items() if k != "metadata" and k != "completions" and k != "model"}
            metadata["writing_instructions"] = prompt
            job_info[job_id]['completed'] = True
            loading_task.cancel()  # b/c we don't want to overwrite the end msg with the loading emojis msg
            dict_init_values['sf_template_name_id']['value'] = piece_name
            await job_end_message(app.client, user_id, core_response, dict_init_values, metadata)

            # Send the articles (each a string) to the user all in one csv file
            await send_csv_articles(app.client, articles, user_id, core_response, logger)

            # send the prompts folder to the user
            # await send_prompt_folder(app.client, temp_dir, user_id, core_response.data['channel'], core_response['ts'], logger)

            # send the variable filled prompt as a .txt file for prompt troubleshooting
            await filled_prompt_to_file(app.client, prompt, core_response, metadata, logger)
            if form_type == "edit":
                pre_edit_article_text = redis_client.get(f"{user_id}_article_text").decode('utf-8')
            print("articles", articles)
            for idx, article in enumerate(articles):
                # get the stats for the article
                # find this article metadata
                article_metadata = output["metadata"][idx]
                article = article.strip()
                chars = len(article)
                tokens = article_metadata["tokens_completion"]
                words = openrouter_engine.word_count(article)
                stats = f"tokens: {tokens}, words: {words}, chars: {chars}"
                
                if form_type == "edit":
                    article = diff_emails(pre_edit_article_text, article)
                # TODO: return txt file of the article then stats next to a button
                await post_article_txt(app.client, core_response, article, stats, logger, temp_directory="/tmp", file_name=f"completion_{idx+1}.txt")
                # every 5 articles, delay for 5 seconds
                if idx != 0 and idx % 5 == 0:
                    await asyncio.sleep(5)
        except Exception as e:
            await stack_trace_message(app.client, user_id, core_response.data['channel'], core_response["ts"], e, logger)
            logger.exception(f"Error generating articles for {user_id}:")
            # end the job
            job_info[job_id]['completed'] = True
        shutil.rmtree(temp_dir)


@app.action("edit_step_button")
async def edit_step_button(ack, body, view, logger):
    await ack()
    channel_id = body["channel"]["id"]
    user_id = body["user"]["id"]
    global monitor_channel_id
    # If the action didn't occur in the monitor channel, return
    if channel_id != monitor_channel_id:
        return
    global init_values, button_states
    global default_folder_path, redis_client, default_template_path, inits_on_first_start
    # print(json.dumps(messages.data['messages'][-5], indent=4))
    try:
        # get the thread_ts from the button press
        thread_ts = body["message"]["thread_ts"]

        # get the button_ts
        button_ts = body["message"]["ts"]

        # get all the messages in the thread
        messages = await app.client.conversations_replies(channel=channel_id, ts=thread_ts)
        # the ts for the first message in the new thread_ts
        thread_ts_ = messages.data["messages"][0]["ts"]
        # save the thread_ts to redis
        redis_client.set(f"{user_id}_thread_ts", thread_ts)
        # find the messages for just this step
        # find the message that contains the button press and keep every message until the next button press
        step_messages = []
        between_step = False
        after_step = False
        step = None
        post_step_messages = []
        for message in messages.data["messages"]:
            # if the message is a button press, then stop adding messages to the list
            if message.get("blocks", [{}])[0].get("accessory", {}).get("action_id", None) == "edit_step_button":
                if between_step is False and float(message["ts"]) == float(button_ts):
                    between_step = True
                    # find the step number
                    step = int(message.get("blocks", [{}])[0].get("accessory", {}).get("text", {}).get("text", "").split(" ")[-1])
                elif between_step is True:
                    # start deleting every message
                    after_step = True
            if after_step:
                # mark the message for deletion
                post_step_messages.append(message["ts"])
            else:
                # if the message is in this step then add it to the list
                if float(message["ts"]) >= float(button_ts):
                    # add the message to the list
                    step_messages.append(message)

        # if step is None, then raise an error
        if step is None or not isinstance(step, int):
            raise Exception("Step not found in the thread")

        # combine step_messages and post_step_messages into a single list
        delete_messages = post_step_messages + [step_message["ts"] for step_message in step_messages]
        redis_client.set(f"{user_id}_delete_messages", json.dumps(delete_messages))

        
        # step_messages[-1] filetype should have the latest.yaml file. If it is then Download it, elif not then look for the first latest.yaml file in the list, else raise error
        # file_id = step_messages[-1]["files"][0]["id"]
        # find the latest.yaml file in the step_messages
        # first check that the last message is a file called latest.yaml
        # if step_messages[-1].get("files", [{"name": None}])[0]["name"] == "latest.yaml":
        #     file_id = step_messages[-1]["files"][0]["id"]
        # else:
        #     # find the first message that contains a file called latest.yaml
        #     for message in step_messages:
        #         if message.get("files", [{"name": None}])[0]["name"] == "latest.yaml":
        #             file_id = message["files"][0]["id"]
        #             break

        # get the first statefile.md file
        file_id = None
        for message in step_messages:
            if message.get("files", [{"name": ""}])[0]["name"].endswith("statefile.md"):
                file_id = message["files"][0]["id"]
                break

        if file_id is None:
            raise Exception("No statefile.md file found in the thread")

        # get the string of the latest.yaml file
        statefile_str = await download_file_content(file_id, os.environ["SLACK_TOKEN"])
        
        # # convert the yaml string to a dict
        # latest_yaml_dict = yaml.load(latest_yaml_str)
        # # import code; code.interact(local=dict(globals(), **locals()))
        # split the yaml string into chunks by back2back prompt_chain.separator s

        # save the latest_yaml_dict to redis
        # redis_client.set(f"{user_id}_latest_yaml_dict", json.dumps(latest_yaml_dict))

        # save the chunks to redis
        redis_client.set(f"{user_id}_latest_statefile_str", statefile_str)
        # save the step to redis
        redis_client.set(f"{user_id}_step", step)


        # # get the step dict
        # step_dict = latest_yaml_dict["prompt_queue"][step-1]
        # # drop all non-default latest_yaml_dict['metadata'] keys
        # step_dict["metadata"] = {k: v for k, v in step_dict["metadata"].items() if k in metadata_defaults or k in ["step"]}

        statefile_chunks = statefile_str.split(prompt_chain.separator+prompt_chain.separator)
        # last chunk is the list of promptsteps, get step-1
        step_dict = json.loads(statefile_chunks[-1])[step-1]
        # print(json.dumps(step_dict, indent=4))
        blocks = []
        
        # plain text input prefilled with name of this step
        block = {
            "type": "input",
            "block_id": "edit_step_name",
            "element": {
                "type": "plain_text_input",
                "action_id": "edit_step_name",
                "initial_value": step_dict["name"]
            },
            "label": {
                "type": "plain_text",
                "text": "Step Name"
            }
        }
        blocks.append(block)

        prompt_text = step_dict["prompt"]
        # model vars
        model_vars = ""
        for k, v in step_dict["metadata"].items():
            model_vars += f"- {k}: {v}\n"
        # each will get its own multiline editable block (or blocks if it's too long)

        # split the prompt_text into chunks
        prompt_chunks = split_text(prompt_text, 3000)
        for i, chunk in enumerate(prompt_chunks):
            if i == 0:
                text = f"Edit Prompt {step}"
            else:
                text = " "
            block = {
                "type": "input",
                "block_id": f"edit_prompt_{i}",
                "element": {
                    "type": "plain_text_input",
                    "action_id": f"edit_prompt_{i}",
                    "multiline": True,
                    "initial_value": chunk
                },
                "label": {
                    "type": "plain_text",
                    "text": text
                }
            }
            blocks.append(block)
        
        # split the model_vars into chunks
        model_vars_chunks = split_text(model_vars, 3000)
        for i, chunk in enumerate(model_vars_chunks):
            if i == 0:
                text = f"Model Variables"
            else:
                text = " "
            block = {
                "type": "input",
                "block_id": f"edit_model_vars_{i}",
                "element": {
                    "type": "plain_text_input",
                    "action_id": f"edit_model_vars_{i}",
                    "multiline": True,
                    "initial_value": chunk
                },
                "label": {
                    "type": "plain_text",
                    "text": text
                }
            }
            blocks.append(block)
        
        #import code; code.interact(local=dict(globals(), **locals()))

        # # convert back to yaml
        # step_yaml_str = dict_to_yaml_str(step_dict, yaml)

        # # display the step_yaml_str in a modal

        # chunks = split_text(step_yaml_str, 3000)
        # block_ = {
        #             "type": "input",
        #             "block_id": "edit_step",
        #             "element": {
        #                 "type": "plain_text_input",
        #                 "action_id": "edit_step",
        #                 "multiline": True,
        #                 "initial_value": " "
        #             },
        #             "label": {
        #                 "type": "plain_text",
        #                 "text": "Edit Step"
        #             }
        #         }
        # blocks = []
        # for i, chunk in enumerate(chunks):
        #     block = copy.deepcopy(block_)
        #     block["element"]["initial_value"] = chunk
        #     if i == 0:
        #         block["label"]["text"] = "Edit Step"
        #     else:
        #         block["label"]["text"] = " "
        #     # increment the block_id
        #     block["block_id"] = f"edit_step_{i}"
        #     blocks.append(block)

        # # add a checkbox to the end of the blocks that increments the prompt queue only one step. 
        # blocks.append({
        #     "type": "input",
        #     "block_id": "increment_prompt_queue",
        #     "optional": True,
        #     "element": {
        #         "type": "checkboxes",
        #         "action_id": "increment_prompt_queue",
        #         "options": [
        #             {
        #                 "text": {
        #                     "type": "plain_text",
        #                     "text": "Increment the prompt queue by exactly one step"
        #                 },
        #                 "value": "value-0"
                        
        #             }
        #         ],
        #         "initial_options": [
        #             {
        #                 "text": {
        #                     "type": "plain_text",
        #                     "text": "Increment the prompt queue by exactly one step"
        #                 },
        #                 "value": "value-0"
        #             }
        #         ]
        #     },
        #     "label": {
        #         "type": "plain_text",
        #         "text": " "
        #     }
        # })

        # add radio buttons to the end of the blocks that allow the user to select the next step or all steps
        blocks.append({
            "type": "input",
            "block_id": "increment_prompt_queue",
            "optional": True,
            "element": {
                "type": "radio_buttons",
                "action_id": "increment_prompt_queue",
                "options": [
                    {
                        "text": {
                            "type": "plain_text",
                            "text": "Run only one step (useful for fast prompt debugging)"
                        },
                        "value": "value-0"
                    },
                    {
                        "text": {
                            "type": "plain_text",
                            "text": "Run all steps from here"
                        },
                        "value": "value-1"
                    }
                ],
                "initial_option": {
                        "text": {
                            "type": "plain_text",
                            "text": "Run only one step (useful for fast prompt debugging)"
                        },
                        "value": "value-0"
                    }
            },
            "label": {
                "type": "plain_text",
                "text": " "
            }
        })


        # open a basic slack form
        try:
            response = await app.client.views_open(
                trigger_id=body["trigger_id"],
                view={
                    "type": "modal",
                    "callback_id": "edit_step_modal_form",
                    "title": {"type": "plain_text", "text": "Edit Step"},
                    "submit": {"type": "plain_text", "text": "Submit"},
                    "blocks": blocks
                }
            )
        except Exception as e:
            logger.exception(f"Error opening edit_step_modal_form for {body['user']['id']}:")
        
    except Exception as e:
        # print the traceback
        traceback.print_exc()
        # print the error
        print(e)
        logger.exception(f"Error editing step for {body['user']['id']}:")
    

@app.view("edit_step_modal_form")
async def handle_form_submission(ack, body, view, logger):
    await ack()
    global yaml, redis_client, inits_on_first_start, init_values, openrouter_engine, prompt_chain, monitor_channel_id
    try:
        # Get form ID
        form_id = view['callback_id']
        # Acknowledge the form submission
        await ack()
        global redis_client, inits_on_first_start, init_values
        user_id = body["user"]["id"]
        # recombine the chunks into a single string
        submitted_data = body["view"]["state"]["values"]
        # edit_step = ""
        # for i in range(100):
        #     if f"edit_step_{i}" in submitted_data:
        #         edit_step = edit_step + submitted_data[f"edit_step_{i}"]["edit_step"]["value"]
        #     else:
        #         break
        step_name = submitted_data["edit_step_name"]["edit_step_name"]["value"]

        edit_step = ""
        for i in range(100):
            if f"edit_prompt_{i}" in submitted_data:
                edit_step = edit_step + '\n' + submitted_data[f"edit_prompt_{i}"][f"edit_prompt_{i}"]["value"]
            else:
                break

        # get the starter variables as well
        step_variables = ""
        for i in range(100):
            if f"edit_model_vars_{i}" in submitted_data:
                step_variables = step_variables + '\n' + submitted_data[f"edit_model_vars_{i}"][f"edit_model_vars_{i}"]["value"]
            else:
                break

        # get the old step settings
        statefile_str = redis_client.get(f"{user_id}_latest_statefile_str").decode('utf-8')
        # get the step
        step = int(redis_client.get(f"{user_id}_step"))
        statefile_chunks = statefile_str.split(prompt_chain.separator+prompt_chain.separator)
        old_promptsteps = json.loads(statefile_chunks[-1])
        
        variables_up_to_this_step = json.loads(statefile_chunks[-2])
        # import code; code.interact(local=dict(globals(), **locals()))
        starter_variables = statefile_chunks[-3]
        starter_variables = prompt_chain.parse_variables_from_text(starter_variables, drop_name_and_prompt=True)
        # md_promptchain_parser check the new step then get_md the new step + the rest of the steps and md_promptchain_parser check again (to get runable variables + promptchain)
        vars_md = prompt_chain.get_md(variables_up_to_this_step, None)
        step_md = vars_md + '\n' + prompt_chain.separator + f" {step_name}" + '\n' + edit_step + '\n' + step_variables
        # check the new step
        try:
            # check the new step in isolation
            parsed_step = prompt_chain.md_promptchain_parser(step_md, models=openrouter_engine.models)
        except Exception as e:
            await ack()
            # raise Exception(f"Error parsing the new step_md: {e}")
            # respond with the error and a fix suggestion
            fix_prompt = f"{md_structure_info}\n\n\n\nFind and fix the following md formatting error found in the below md file:\n\nFile:\n{step_md}\n\n\nError:\n\n{e}\n\nBe very concise with the fix. DO NOT PRINT OUT THE ENTIRE FILE. Explain the fix like I'm 5. Let's think step by step. SHORT LOGICAL FIX:"
            fix_task = await openrouter_engine.acomplete(fix_prompt, model="anthropic/claude-3-haiku:beta", max_tokens=40, temperature=0.20, completions=1)
            fix = fix_task["completions"][0]
            error_msg = f"MD Error: {e}\n\n\nSuggested Fix: {fix}"
            # create dummy core_response object. core_response must have a .data attribute and be a dict
            class CoreResponse:
                def __init__(self):
                    self.data = {}

                def __getitem__(self, key):
                    return getattr(self, key)

                def __setitem__(self, key, value):
                    setattr(self, key, value)
            
            core_response = CoreResponse()
            core_response.data['channel'] = monitor_channel_id
            core_response['ts'] = str(redis_client.get(f"{user_id}_thread_ts"))
            # send the error_msg to the user
            await string_to_slack(app.client, error_msg, core_response, logger, initial_comment=" ", file_name=f"step_{step}_error.txt")
            return
        await ack()
        old_promptsteps_ = copy.deepcopy(old_promptsteps)
        # get the new step and replace the old step in the promptsteps
        # import code; code.interact(local=dict(globals(), **locals()))
        old_promptsteps[step-1] = parsed_step["promptchain"][0]
        # remove all earlier steps 
        old_promptsteps = old_promptsteps[step-1:]
        new_promptsteps = copy.deepcopy(old_promptsteps)
        # keep earlier step(step-1 non-inclusive)
        if step >= 2:
            old_promptsteps_ = old_promptsteps_[:step-1]
        else:
            old_promptsteps_ = []
        # delete the messages from the thread
        delete_messages = json.loads(redis_client.get(f"{user_id}_delete_messages"))

        # delete the messages in parallel
        delete_tasks = []
        for message_ts in delete_messages:
            delete_tasks.append(asyncio.create_task(app.client.chat_delete(channel=monitor_channel_id, ts=message_ts)))
        await asyncio.gather(*delete_tasks)

        # # delete the messages in serial
        # for message_ts in post_step_messages:
        #     await app.client.chat_delete(channel=monitor_channel_id, ts=message_ts)
        #import code; code.interact(local=dict(globals(), **locals()))

        queue_edit = {
            "step": step,
            "variables_up_to_this_step": variables_up_to_this_step,
            "new_promptsteps": new_promptsteps,
            "old_promptsteps": old_promptsteps_,
            "starter_variables": starter_variables,
            "not_executable_promptsteps": [],
            # thread_ts is the thread_ts of the button press
            "thread_ts": redis_client.get(f"{user_id}_thread_ts"),
            # increment the prompt_queue by just and only one step
            "increment_prompt_queue": submitted_data["increment_prompt_queue"]["increment_prompt_queue"]["selected_option"]['value'] == "value-0"
        }

        # jump into process_form_submission
        form_type = "null"
        await process_form_submission(form_type, ack, body, view, logger, queue_edit=queue_edit)

    except Exception as e:
        # print the traceback
        traceback.print_exc()
        # print the error
        print(e)
        logger.exception(f"Error editing step for {body['user']['id']}:")


@app.view("copy_generator_modal_form")
@app.view("copy_generator_modal_form_edit")
async def handle_form_submission(ack, body, view, logger):
    # Get form ID
    form_id = view['callback_id']
    if form_id in ["copy_generator_modal_form_edit"]: 
        form_type = "edit"
        await process_form_submission(form_type, ack, body, view, logger)
    else:
        global redis_client, inits_on_first_start, init_values
        user_id = body["user"]["id"]
        # action_id = body['actions'][0]['action_id']
        user_init_values = await get_user_init_values(user_id, init_values, redis_client, inits_on_first_start)
        temp_dir = get_user_prompts_folder(user_id, redis_client, default_folder_path, logger, inits_on_first_start)
        # print('1 user_init_values["template_buttons"]["visable"]', user_init_values["template_buttons"]["visable"])
        submitted_data = body["view"]["state"]["values"]
        dict_init_values = form2init_values_list(submitted_data, user_init_values, temp_dir, button_states, action_taken=None)
        if False and dict_init_values["sf_template_name_id"]["value"] in [init_values["sf_template_name_id"]["value"], ""]:
            # send a etherial message to the user stating that they need to fill out a new sf_template_name_id
            await app.client.chat_postEphemeral(
                channel=monitor_channels[0],
                user=user_id,
                text="Please fill out a new SF Template Name Id field before submitting the form."
            )
            return
        else:
            form_type = "submission"
            # Process the form submission
            await process_form_submission(form_type, ack, body, view, logger)

@app.action("Edit_templates")
@app.action("template")
@app.action("folder_1")
@app.action("folder_2")
@app.action("variables")
@app.action("template_button_prompt")
@app.action("folder_1_button_prompt")
@app.action("folder_2_button_prompt")
@app.action("variables_button_prompt")
@app.action("template_button_info")
@app.action("folder_1_button_info")
@app.action("folder_2_button_info")
@app.action("variables_button_info")
@app.action("template_button_Save_changes")
@app.action("folder_1_button_Save_changes")
@app.action("folder_2_button_Save_changes")
@app.action("variables_button_Save_changes")
@app.action("template_button_rename")
@app.action("folder_1_button_rename")
@app.action("folder_2_button_rename")
@app.action("variables_button_rename")
@app.action("template_button_create_new")
@app.action("folder_1_button_create_new")
@app.action("folder_2_button_create_new")
@app.action("variables_button_create_new")
@app.action("template_button_delete")
@app.action("folder_1_button_delete")
@app.action("folder_2_button_delete")
@app.action("variables_button_delete")
@app.action("start/copy_from_template")
@app.action("start/copy_from_folder_1")
@app.action("start/copy_from_folder_2")
@app.action("preview_checkbox")
@app.action("prompt_queue_checkbox")
@app.action("model")
async def rerender_form(ack, body, view, logger):
    # Acknowledge the form submission
    await ack()
    global job_info, init_values, redis_client, inits_on_first_start, default_folder_path, default_template_path, button_states, openrouter_engine
    try:
        get_models_task = asyncio.create_task(openrouter_engine.openrouter_checkup())
        # print("default_folder_path", default_folder_path)
        submitted_data = body["view"]["state"]["values"]
        user_id = body["user"]["id"]
        action_id = body['actions'][0]['action_id']
        # form_id = view['callback_id']
        # Convert the submitted_data to init_values
        # print("inits_on_first_start", inits_on_first_start)
        user_init_values = await get_user_init_values(user_id, init_values, redis_client, inits_on_first_start)
        temp_dir = get_user_prompts_folder(user_id, redis_client, default_folder_path, logger, inits_on_first_start)
        # print('1 user_init_values["template_buttons"]["visable"]', user_init_values["template_buttons"]["visable"])

        dict_init_values = form2init_values_list(submitted_data, user_init_values, temp_dir, button_states, action_taken=action_id)
        if action_id == "model":
            # add a text block to dict_init_values containing information about the model
            model_info = openrouter_engine.models[dict_init_values["model"]["value"]]
            # drop per_request_limits from model_info
            model_info = {k: v for k, v in model_info.items() if k != "per_request_limits"}
            # I want the new key value to be inserted last in dict_init_values
            dict_init_values = {**dict_init_values, "model_data": {"block_text": "model data", "visable": True, "value": json.dumps(model_info, indent=8), "form_search_key": "selected_option/text/text", "block_type": "text", "action_id": "model_data_0"}}
        else: 
            # remove the model_data key from dict_init_values
            dict_init_values.pop("model_data", None)
        # print('2 user_init_values["template_buttons"]["visable"]', dict_init_values["template_buttons"]["visable"])

        new_default_template_path = build_new_default_template_path(dict_init_values)
        # save new_default_template_path to redis so that when they open a new form, it will allign with the new dict_init_values
        redis_client.set(f"{user_id}_default_template_path", new_default_template_path)
        # save temp_dir to redis to allow for the user to edit the prompts
        # Save the default_folder_dict to a temporary directory
        temp_dir = save_to_temp_folder(folder_to_dict(temp_dir), os.path.basename(temp_dir))
        # redis_client.set(f"{user_id}_prompts_folder", pickle.dumps(folder_to_dict(temp_dir)))
        # print out all the folders and files of the temp_dir folder
        # # print(f"temp_dir: {temp_dir}")
        # # print(f"temp_dir folders: {os.listdir(temp_dir)}")
        # # print(f"temp_dir files: {os.listdir(os.path.join(temp_dir, 'templates'))}")
        
        dict_init_values = model_dict_fill_prompt(dict_init_values, temp_dir, button_states)
        # if the sf_template_name_id or writing_instructions are an empty string then add a period to the value
        if dict_init_values["sf_template_name_id"]["value"] in ["", None]:
            dict_init_values["sf_template_name_id"]["value"] = "."
        if dict_init_values["writing_instructions"]["value"] in ["", None]:
            dict_init_values["writing_instructions"]["value"] = "."

        # drop the error key from the dict_init_values. If there is no error, this will do nothing
        dict_init_values.pop("error", None)

        model_options = openrouter_engine.slack_block_model_list()
        new_view = await build_form_v2(dict_init_values, debug=True, model_options=model_options)
        # # print(json.dumps(new_view))
        old_view = view
        await update_form(client, body, old_view, json.dumps(new_view), logger)
        # save the dict_init_values in Redis for the user
        redis_client.set(f"{user_id}_prompts_folder", pickle.dumps(folder_to_dict(temp_dir)))
        # user_init_values["template_buttons"]["visable"]
        # print('3 user_init_values["template_buttons"]["visable"]', dict_init_values["template_buttons"]["visable"])
        redis_client.set(f"{user_id}_job_form", json.dumps(dict_init_values))
        await get_models_task
    except SlackApiError as e:
        error_msg = f"Error opening the form {user_id}:"
        logger.exception(error_msg)

@app.action("open_form")
async def handle_open_form(ack, body, logger):
    await ack()
    channel_id = body["channel"]["id"]
    user_id = body["user"]["id"]
    global monitor_channel_id
    # If the action didn't occur in the monitor channel, return
    if channel_id != monitor_channel_id:
        return
    global init_values, button_states
    global default_folder_path, redis_client, default_template_path, inits_on_first_start, openrouter_engine
    try:
        user_init_values = await get_user_init_values(user_id, init_values, redis_client, inits_on_first_start)
        
        temp_dir = get_user_prompts_folder(user_id, redis_client, default_folder_path, logger, inits_on_first_start)
        # if not inits_on_first_start:
        #     # get default_template_path from redis
        #     default_template_path = redis_client.get(f"{user_id}_default_template_path")  # .decode('utf-8')
        #     # print("default_template_path in if", default_template_path)
        # else:
        #     default_template_path = build_new_default_template_path(user_init_values)
        #     # print("default_template_path in else", default_template_path)

        # I'll be honest. I don't know why I had the above if else checks
        default_template_path = build_new_default_template_path(user_init_values)
        

        # need to make a prompt to show to the user. Its a method in article_writer
        
        user_init_values = model_dict_fill_prompt(user_init_values, temp_dir, button_states)
        
        # if the sf_template_name_id or writing_instructions are an empty string then add a period to the value
        if user_init_values["sf_template_name_id"]["value"] in ["", None]:
            user_init_values["sf_template_name_id"]["value"] = "."
        if user_init_values["writing_instructions"]["value"] in ["", None]:
            user_init_values["writing_instructions"]["value"] = "."
        model_options = openrouter_engine.slack_block_model_list()
        view = await build_form(user_init_values, temp_dir, default_template_path, model_options=model_options)
        # view = await build_form_v2(user_init_values)
        # print(json.dumps(view))
        try:
            print(json.dumps(view))
            
            view = ensure_view_size(view)
            print("\n\n\n\nnew view")
            print(json.dumps(view))
        except Exception as e:
            print(e)
            # save program state to pickle file to debug later
            pickle.dump(view, open("./errors/ensure_view_size.pkl", "wb"))
            view = await build_form_v2(inits_on_first_start, model_options=model_options)
            # how to open pickle file in a code interpreter
            # import pickle
            # pickle.load(open("ensure_view_size.pkl", "rb"))
            # import code; code.interact(local=dict(globals(), **locals()))
            # raise e
        try:
            await send_form(client, body, view, logger)
        except Exception as e:
            print(e)
            # save program state to pickle file to debug later
            pickle.dump(view, open("./errors/send_form.pkl", "wb"))
            # how to open pickle file in a code interpreter
            # import pickle
            # view = pickle.load(open("./errors/send_form.pkl", "rb"))
            # import code; code.interact(local=dict(globals(), **locals()))
            # raise e
            # send SOMTHING to the user
            view = await build_form_v2(inits_on_first_start, model_options=model_options)
            await send_form(client, body, view, logger)
        inits_on_first_start = False
        redis_client.set(f"{user_id}_prompts_folder", pickle.dumps(folder_to_dict(temp_dir)))
        
        redis_client.set(f"{user_id}_default_template_path", default_template_path)

        redis_client.set(f"{user_id}_job_form", json.dumps(user_init_values))
    except SlackApiError as e:
        error_msg = f"Error opening the form for {user_id}:"
        # if the error is not expired_trigger_id, then log it
        if e.response.get("error", None) != "expired_trigger_id" and \
            e.response.get("error", None) != "not_found":
            logger.exception(error_msg)
    except TypeError as e:
        # if TypeError: object of type 'NoneType' has no len() then close the form
        print(e)
        if str(e) == "object of type 'NoneType' has no len()":
            await app.client.views_push(
                trigger_id=body["trigger_id"],
                view={
                    "type": "home",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "Close and reopen form to continue."
                            }
                        }
                    ]
                }
            )
    except Exception as e:
        # print the traceback
        traceback.print_exc()
        # print the error
        print(e)
        logger.exception(f"Error opening the form for {user_id}:")

def model_dict_fill_prompt(model_dict, temp_dir, button_states):
    # get the prompt from the model
    template_selections = None
    if model_dict["template"]["value"] != "None":
        template_selections = get_template_selections(None, model_dict, default_folder_path, button_states)

        prompt_variables = {"email_examples": "", "writing_instructions": model_dict["writing_instructions"]["value"]}

        aw = article_writer.ArticleWriter(model_name=model_dict["model"]["value"], temp=0)
        output = aw.create_template(temp_dir, template_selections, prompt_variables=prompt_variables, model_dict=model_dict)
        # print(output)
        
    else:
        # model_dict["preview"]["value"] = str(model_dict["writing_instructions"]["value"])
        output = str(model_dict["writing_instructions"]["value"])
    # print(model_dict["preview"])
   
    
    # model_dict["preview"]["value"] = output
    # print('model_dict["preview"]["value"]', model_dict["preview"]["value"])
    # slack text blocks need do have less than 3000 characters so we need to split the output into chunks

    output_chunks = split_text(output, 3000)
    # for each chunk, add a text block to the model_dict
    # the first chunk will fill the preview value and following chunks will be a copy of the preview but inserted into the dict after the preview
    # name the extra keys preview_1, preview_2, etc
    # deepcopy of preview
    # remove every key with preview_ in it except for preview_checkbox
    for key in list(model_dict.keys()):
        if "preview_" in key and key != "preview_checkbox":
            del model_dict[key]
    deep_preview = copy.deepcopy(model_dict["preview"])
    for i, chunk in enumerate(output_chunks):
        # create a new copy of the deep_preview
        deep_preview_ = copy.deepcopy(deep_preview)
        deep_preview_["action_id"] = f"preview_{i}"

        # need to insert the new key directly after the last preview key
        if i == 0:
            model_dict["preview"]["value"] = chunk
        else:
            key_to_insert_after = f"preview_{i-1}" if i > 1 else "preview"
            key_to_insert = f"preview_{i}"
            deep_preview_["value"] = chunk
            value_to_insert = deep_preview_
            def insert_after_key(original_dict, key_to_insert_after, key_to_insert, value_to_insert):
                new_dict = {}
                for key, value in original_dict.items():
                    new_dict[key] = value
                    if key == key_to_insert_after:
                        new_dict[key_to_insert] = value_to_insert
                return new_dict
            model_dict = insert_after_key(model_dict, key_to_insert_after, key_to_insert, value_to_insert)
    # print(model_dict)
    
    return model_dict

@app.action("edit_piece")
async def handle_edit_piece(ack, body, logger):
    await ack()
    channel_id = body["channel"]["id"]
    user_id = body["user"]["id"]
    global monitor_channel_id
    # If the action didn't occur in the monitor channel, return
    if channel_id != monitor_channel_id:
        return
    global init_values, rewrite_preset_prompt
    global default_folder_path, redis_client, default_template_path, inits_on_first_start, openrouter_engine
    try:
        # Get the user's init_values from Redis
        user_init_values_json = redis_client.get(f"{user_id}_job_form")
        # save the article text to redis. We first need to clean all the text which show version changes/edits
        edited_email_text = get_edited_email(body["message"]["blocks"][0]["text"]["text"])
        redis_client.set(f"{user_id}_article_text", edited_email_text)
        # If user_init_values_json is not None, load the user's init_values
        if user_init_values_json:
            user_init_values = json.loads(user_init_values_json)
            # If the user's init_values are not of the same type or lenght as the base init_values, use the base init_values
            if type(user_init_values) != type(init_values) or len(user_init_values) != len(init_values):
                user_init_values = init_values
        else:
            user_init_values = init_values
        # Set the new value for user_init_values[2]
        user_init_values["writing_instructions"]["value"] = rewrite_preset_prompt + edited_email_text
        temp_dir = get_user_prompts_folder(user_id, redis_client, default_folder_path, logger, inits_on_first_start)
        model_options = openrouter_engine.slack_block_model_list()
        view = await build_form(user_init_values, temp_dir, default_template_path, edit_form=True, model_options=model_options)
        await send_form(client, body, view, logger)
    except SlackApiError as e:
        error_msg = f"Error opening the form {user_id}:"
        logger.exception(error_msg)


# @app.action("model")
# async def handle_some_action(ack, body, logger):
#     await ack()
#     logger.info(body)

@app.action("temperature")
async def handle_some_action(ack, body, logger):
    await ack()
    logger.info(body)

@app.action("samples")
async def handle_some_action(ack, body, logger):
    await ack()
    logger.info(body)

# async def handle_some_action(ack, body, logger):
#     await ack()
#     logger.info(body)
    

@app.event("app_mention")
@app.event("message")
async def handle_message_events(ack, body, logger):
    await ack()
    logger.info(body)
    try:
        # print the event type
        # print(body['event']['type'])
        event_id = body['event']['event_ts']
        # track the current time to get a unique timestamp for each event
        # current_time = str(time.time())
        # event_id = f"{event_id}"
        if event_id in processed_events:
            # This event has already been processed, so ignore it
            return
        # Add the event ID to the set of processed events
        processed_events.add(event_id)

        global monitor_channel_id, slack_custom_actions_toolbox
        # if the message is not in target channel then exit. Also exit if the message is from the bot itself
        channel_id = body['event']['channel']
        if channel_id != monitor_channel_id or body['event'].get('bot_id', None) is not None:
            return
        thread_ts = body['event'].get('thread_ts', None)
        if thread_ts is None:
            thread_ts = body['event'].get('ts', None)
        is_thread = thread_ts is not None

        # If it's a thread and the total thread messages are greater than 6
        # and the first message in the thread is from the bot AND the last message is addressed to the bot, get the previous messages

        # if body['event'].get('text', None) is not None and \
        #     (body['event']['text'].startswith(f"<@{slack_custom_actions_toolbox.bot_id}> subjectline") or \
        #     body['event']['text'].startswith(f"<@{slack_custom_actions_toolbox.bot_id}> Subjectline")):

        #     print("gen_headlines_from_message")
        #     thread_ts = body['event'].get('ts', None)
        #     engine = ore.OpenrouterEngine(checkup=False)
        #     engine.models = openrouter_engine.models
        #     # Schedule gen_headlines_from_message to run on the event loop
        #     asyncio.create_task(gen_headlines_from_message(body, logger, client, thread_ts, slack_custom_actions_toolbox, engine))
        if body['event'].get('text', None) is not None and \
            body['event']['text'].startswith(f"<@{slack_custom_actions_toolbox.bot_id}>"):
            print("thread_bot_responder")
            engine = ore.OpenrouterEngine(checkup=False)
            engine.models = openrouter_engine.models
            asyncio.create_task(thread_bot_responder(body, client, app, channel_id, thread_ts, logger, redis_client, slack_custom_actions_toolbox, engine, cached_content=None))
        # elif body['event'].get('text', None) is not None and \
        #     body['event']['text'].startswith(f"<@{slack_custom_actions_toolbox.bot_id}> restart"):
        #     # restart this server
        #     print("restarting server")
        #     await app.client.chat_postMessage(
        #         channel=monitor_channel_id,
        #         text="Restarting the server..."
        #     )
        #     # restart the main process
                       
    except SlackApiError as e:
        print("Queue size:", slack_custom_actions_toolbox.message_handler.log_queue.qsize())
        logger.exception(f"Error handling message events:")
        print("Queue size:", slack_custom_actions_toolbox.message_handler.log_queue.qsize())


async def main():
    logger.info("Starting the application")
    print("After logging")
    print(logger.level)

    handler = AsyncSocketModeHandler(app, os.environ["WEBSOCKET_TOKEN"])
    print("After handler")
    # Initialize 
    try:
        await slack_custom_actions_toolbox.initialize()
    except Exception as e:
        print(f"Error when initializing: {e}")
        return
    print("After initialize")
    # Create tasks for start_async and send_log_messages
    # wait until self.models dictionary is populated. Can't await start_task because it's an inf loop
    async def wait_for_models(): 
        while True:
            await asyncio.sleep(10)
            prompt_chain.models = openrouter_engine.models
            # print(len(prompt_chain.models.keys()))
        print("Models first loaded")

    
    task1 = asyncio.create_task(handler.start_async())
    task2 = asyncio.create_task(slack_custom_actions_toolbox.send_log_messages())
    task3 = asyncio.create_task(openrouter_engine.hourly_model_checkup(check_every=60*60))
    task5 = asyncio.create_task(wait_for_models())
    print("After tasks")
    print("Handlers:", logger.handlers)  # Print handlers
    print(logger.level)
    for handler_ in logger.handlers:
        print(handler_.level)
        
    # Wait for the tasks to complete
    await asyncio.gather(task1, task2, task3, task5)


if __name__ == "__main__":
    # send a simple slack startup message to the monitor channel
    # remember that app = AsyncApp(token=os.environ["SLACK_TOKEN"])
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Starting up..."
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
        }
    ]
    ## if monitor_channels[0] == "pytesting":
    async def send_startup_message():
        response = await app.client.chat_postMessage(
        channel=monitor_channels[0],
        text="Starting up...",
        blocks=blocks
    )
    response = asyncio.run(send_startup_message())
    print(response)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nApplication shut down gracefully.")

    # # await slack_custom_actions_toolbox.initialize()
    # admin_dev_id = "U02C7JSMSMS"
    # # debug a user
    # user_id = "USA8ZMYG7"
    # # user_init_values_json = redis_client.get(f"{user_id}_job_form")
    # # user_prompts_folder = redis_client.get(f"{user_id}_prompts_folder")
    # # user_init_values = json.loads(user_init_values_json)
    # # # save the folder to this directory

    # # 
    # # # save the user's prompt folder and job form to the admin's redis for debugging
    # # redis_client.set(f"{admin_dev_id}_job_form", user_init_values_json)
    # # redis_client.set(f"{admin_dev_id}_prompts_folder", user_prompts_folder)
    
    # # await send_form_trigger_message(monitor_channels[0])
