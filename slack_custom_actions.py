import os, time, shelve
import json, traceback
from slack_sdk.errors import SlackApiError
from slack_bolt.adapter.socket_mode import SocketModeHandler
from pathlib import Path
import time
from datetime import datetime
import asyncio
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
import queue
from queue import Empty
import aiohttp
from aiohttp import ClientSession

class SlackCustomActions:
    def __init__(self, application, handler, message_handler, how_to_guide='', logging_channel=None, pr=False):
        self.how_to_guide = how_to_guide
        self.app = application
        self.handler = handler
        self.message_handler = message_handler
        self.bot_id = None  # Initialize as None; we'll set it later in an async method
        self.slack_names = []  # Initialize as empty; we'll populate it later in an async method
        self.logging_channel = logging_channel

    async def restart_bot(self, pr=False):
        if pr: print("Restarting bot")
        await self.app.client.chat_postMessage(channel=self.bot_id, text=f"Restarting bot")
        self.handler.stop()
        await self.handler.start_async()
        await self.app.client.chat_postMessage(channel=self.bot_id, text=f"Bot restarted")
    
    async def send_log_message(self, message, pr=False):
        if pr: print(f"Sending log message: {message}")
        if self.logging_channel is not None:
            await self.app.client.chat_postMessage(
                channel=self.logging_channel,
                text=message
            )

    async def send_log_messages(self, pr=False):
        if pr: print("Starting SlackCustomActions.send_log_messages")
        while True:
            try:
                if pr: print("Queue size:", self.message_handler.log_queue.qsize())
                message = self.message_handler.log_queue.get_nowait()
                if pr: print(f"Message retrieved from queue: {message}")
                await self.send_log_message(message)
            except Empty:
                # No messages in the queue, sleep for a bit before trying again
                if pr: print("No messages in the queue, sleeping for 1 second")
                await asyncio.sleep(1)
    
    async def initialize(self, pr=False):
        print("Initializing SlackCustomActions")
        result = await self.app.client.auth_test()
        print(result)
        self.bot_id = result["user_id"]
        print(self.bot_id)
        self.repeat = 0
        try:
            with shelve.open('mydatabase.db') as db:
                record = db.get('record', (0, None))
                if pr: print(f"Record retrieved: {record[1]}") 
                else: print("Record retrieved")
                if time.time() - record[0] < 600:
                    print("Record found and less than 10 minutes old")
                    self.slack_names = record[1]
                else:
                    print("No record found or older than 10 minutes. Pulling from Slack API")

                    # subject to rate limiting
                    attempts = 5
                    wait_time = 5
                    for i in range(attempts):
                        try:
                            result = await self.app.client.users_list()
                            save_list = result['members']
                            break
                        except Exception as e:
                            if i < attempts-1:
                                print(e, f"trying again in {str(wait_time)} seconds")
                                time.sleep(wait_time)
                            else:
                                raise(f"{e} call failed {str(attempts)} times")
                    
                    for user in save_list:
                        if not user['deleted'] and (user['profile']['real_name'] != '' or user['id'] == self.bot_id):
                            
                            if user['id'] == self.bot_id:
                                self.slack_names.append({user['profile']['real_name']: {'real_name': user['profile']['real_name'], 'id': user['id']}})
                            else:
                                if user['profile']['display_name'] == '':
                                    self.slack_names.append({user['profile']['real_name']: {'real_name': user['profile']['real_name'], 'id': user['id']}})
                                else:
                                    self.slack_names.append({user['profile']['display_name']: {'real_name': user['profile']['real_name'], 'id': user['id']}})
                    db['record'] = (time.time(), self.slack_names)
        except Exception as e:
            print(f"Error: {e}")
            if os.path.exists('mydatabase.db'):
                os.remove('mydatabase.db')
            if self.repeat < 1:
                return await self.initialize(pr)
        """user_id = self.id_finder("Barrett Velker")
        convo_id_ = self.get_dm_convo_id(user_id, pr=True)
        # now get the dm history between the bot and a user
        messages = self.get_dm_user_history(convo_id_, user_id, pr=True)
        self.get_thread_replies(convo_id_, messages[0]['ts'], pr=True)
        raise Exception("stop")"""
        #print(self.slack_names)

    async def get_thread_replies(self, convo_id, ts, pr=False):
        try:
            results = await self.app.client.conversations_replies(channel=convo_id, ts=ts)
            if pr: print(results)
            raise Exception("stop")
        except SlackApiError as e:
            print(f"Error: {e}")

    async def get_dm_convo_history(self, usr_id, limit=100, stopping_params=True, pr=False):
        # get list of all the messages (if it's a thread then just scan the first message) that are made by the user
        # stop when you find a context text file
        convo_id = self.get_dm_convo_id(usr_id)
        if pr: print(convo_id)
        results = await self.app.client.conversations_history(channel=convo_id, limit=limit)
        if pr: print(results)
        # get the user, text tuples
        # convert each user_id to their base name
        hist = []
        for idx, message in enumerate(results['messages']):
            if pr: print(message)
            if stopping_params and idx != 0 and (("files" in message and message["files"][0]['filetype'] == 'text') or message['text'].lower() == 'clear'):
                break
            if message['text'].strip() != '' and message['text'].lower() != 'clear':
                dt_object = datetime.fromtimestamp(int(float(message['ts'])))
                hist.append((self.display_name_finder(message['user']), message['text'], f"{dt_object:%d-%m-%Y %H:%M:%S}"))
        return hist

    async def get_dm_convo_id(self, user_id, pr=False):
        convo_id = None
        try:
            # print(app.client.conversations_list())
            # Call the conversations.list method using the WebClient
            results = await self.app.client.conversations_list(limit=100, types="im", exclude_archived=True)
            if pr: print(results)
            if results['ok']:
                for convo in results['channels']:
                    if not convo['is_user_deleted'] and convo['user'] == user_id:
                        convo_id = convo['id']
                        if pr: print(convo_id)
                        break
        except SlackApiError as e:
            print(f"Error: {e}")
        return convo_id

    def id_finder(self, display_name):
        # search self.slack_names (list of dicts) for any matching names
        matches = 0
        for user in self.slack_names:
            # print(list(user.keys())[0])
            # get the key in the dict
            if str(list(user.keys())[0]) == display_name:
                matches += 1
                user_data = user[display_name]['id']

        if matches != 1:
            raise Exception(f'id_finder: {str(matches)} matches found for display_name:{display_name}')
        else:
            return user_data

    def display_name_finder(self, user_id):
        # search self.slack_names (list of dicts) for any matching names
        matches = 0
        display_name = ''
        for user in self.slack_names:
            # print(list(user.keys())[0])
            # get the key in the dict
            if user[str(list(user.keys())[0])]['id'] == user_id:
                matches += 1
                display_name = str(list(user.keys())[0])
        if matches != 1:
            raise Exception(f'id_finder: {str(matches)} matches found for user_id:{user_id}')
        else:
            return display_name

    def get_users(self):
        users = []
        for user in self.slack_names:
            users.append(str(list(user.keys())[0]))
        return users

    async def run(self):
        if self.how_to_guide != '':
            reply = await self.app.client.chat_postMessage(channel=self.bot_id, text=f"{self.bot_id} is online!")
            await self.app.client.chat_postMessage(channel=self.bot_id, thread_ts=reply['ts'],
                                             text=self.how_to_guide)
        self.handler.start()

    async def get_convo_id(self, channel_name, pr=False):
        # THIS IS A SKETCHY METHOD THAT IS NOT GUARANTEED TO WORK EVERY TIME
        conversation_id = None
        try:
            # print(app.client.conversations_list())
            # Call the conversations.list method using the WebClient
            convo_list = await self.app.client.conversations_list(limit=500, types="public_channel, private_channel", exclude_archived=True)
            # print(convo_list)
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
                stack_trace = traceback.format_exc()
                raise Exception(f"get_convo_id Channel {channel_name} not found. Stack Trace: {stack_trace}")
        except SlackApiError as e:
            print(f"Error: {e}")
        return conversation_id

    async def get_convo_context(self, channel_id, max_chars=1500, max_messages=100, pr=False):
        # 9 chars consistant identifier for each chat participant
        # Store conversation history
        convo_hist = []
        # ID of the channel you want to send the message to
        try:
            # Call the conversations.history method using the WebClient
            # conversations.history returns the first 100 messages by default
            # These results are paginated, see: https://api.slack.com/methods/conversations.history$pagination
            result = await self.app.client.conversations_history(channel=channel_id)
            # unfold the messages until we fill up the max_chars

            convo_hist = result["messages"]
            context_ = ''
            index = 0
            while max_chars > len(context_) and len(convo_hist) > index and index < max_messages:
                context_ = f'\n<@{convo_hist[index]["user"]}>: {convo_hist[index]["text"]}\n{context_}'
                index += 1
            context_ = context_ + '\n\n'
            if pr: print(context_)
            # Print results
            # print(json.dumps(convo_hist, indent=4))
            if pr: print(f"{len(convo_hist)} messages found in {channel_id}")
        except SlackApiError as e:
            print(f"Error: {e}")
            context_ = None
        return context_

    async def get_users(self, channel_id, pr=False):
        # get the users in the channel
        users = []
        try:
            # Call the conversations.members method using the WebClient
            result = await self.app.client.conversations_members(channel=channel_id)
            result = result["members"]
            if pr: print(result)
            # Print results
            # print(json.dumps(result, indent=4))
            # users = result["members"]
            return result
        except SlackApiError as e:
            print(f"Error: {e}")

    async def get_user_messages(self, user, channel_id, max_messages=5, pr=True):
        # by default get the last message from the user in the channel
        # ID of the channel to get history
        # return the last max_messages messages from the user in the channel
        # returns the messages of the user as a list of strings where the first element is the most recent message
        try:
            # Call the conversations.history method using the WebClient
            # The client passes the token you included in initialization
            result = await self.app.client.conversations_history(channel=channel_id)
            # unfold the messages until we fill up the max_chars
            convo_hist = result["messages"]
            user_msgs = []
            index = 0
            msg_counter = 0
            while len(convo_hist) > index:
                if convo_hist[index]["user"] == user and msg_counter < max_messages:
                    user_msgs.append(convo_hist[index])
                    msg_counter += 1
                index += 1
            # Print results
            # print(json.dumps(convo_hist, indent=4))
            if pr: print(f"{len(user_msgs)} messages found from {user} in {channel_id}")
        except SlackApiError as e:
            print(f"Error: {e}")
            user_msgs = []
        return user_msgs


if __name__ == "__main__":
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    import os
    from pathlib import Path
    from dotenv import load_dotenv

    env_path = Path('.') / '.env.wordle'
    load_dotenv(dotenv_path=env_path)  # for some reason need these previous two lines for os.environ to work


    app = App(token=os.environ["SLACK_TOKEN"])

    # Create a SocketModeHandler instance
    handler = SocketModeHandler(app, os.environ["WEBSOCKET_TOKEN"])

    # Start Socket Mode
    # handler.start()

    async def run():
        # also make an instance the standard slack client
        slack_custom_actions = ssb.SlackCustomActions(app, how_to_guide='', pr=True)
        channel_name = 'team--leesburg'
        # channel_name = 'winningteam'
        # Get the conversation ID
        conversation_id = get_convo_id(channel_name, pr=True)
        print(conversation_id)
        # conversation_id = "C05GWS1KJ10"
        context = await slack_custom_actions.get_convo_context(conversation_id, pr=True)
        print(context)
        import code; code.interact(local=dict(globals(), **locals()))
    asyncio.run(run())

    # Create a SlackCustomActions instance
    slack_custom_actions = SlackCustomActions(app, how_to_guide='', pr=True)
    channel_name = 'team-leesburg'
    # Get the conversation ID
    conversation_id = slack_custom_actions.get_convo_id(channel_name, pr=True)
    print(conversation_id)
    context = slack_custom_actions.get_convo_context(conversation_id, pr=True)
    print(context)
    # raise Exception(slack_custom_actions)
    # print(slack_custom_actions.get_dm_convo_history('U02C7JSMSMS', limit=100, stopping_params=False))
    # id_finder = "Barrett Velker"
    # print(slack_custom_actions.id_finder(id_finder), id_finder)


    # # Get the conversation context

    # # Get the users in the channel
    # users = slack_custom_actions.get_users(conversation_id)
    # print(users)

    # # Get the last message from the user in the channel
    # user_msgs = slack_custom_actions.get_user_messages(users[0], conversation_id, pr=True)

    # # print(user_msgs)

    # # print(str(app.client.users_list()))  # U02C7JSMSMS U04L6EKVBNY
    # # print(app.client.conversations_open(users='U02C7JSMSMS', prevent_creation=False))
    # print(app.client.chat_postMessage(channel='U02C7JSMSMS', text=f"Test message"))

    # # print(app.client.users_identity("@Barrett Velker"))
    # # print(app.client.users_list())

    # # from users_list() (a dict of dicts) create tuples of the values in ("display_name", "id")
    # # itterate through users_list
    # save_list = app.client.users_list()['members']
    # # print(save_list)
    # slack_names = []
    # for user in save_list:
    #     if not user['deleted'] and user['profile']['display_name'] != '':
    #         print({user['profile']['display_name']: {'real_name': user['profile']['real_name'], 'id': user['id']}})
    #         slack_names.append({user['profile']['display_name']: {'real_name': user['profile']['real_name'], 'id': user['id']}})
        
    # print(slack_names)

