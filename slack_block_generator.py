import os
import json
from pathlib import Path

class SlackBlockGeneratorV2:
    def __init__(self, initial_values):
        self.initial_values = initial_values
    
    def generate_dropdown_block(self, parent_folder, initial_value, action_id, options):        
        initial_option = next((opt for opt in options if opt["value"] == initial_value), None)
        if not initial_option and options:
            initial_option = options[0]

        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": parent_folder
            },
            "accessory": {
                "type": "static_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Select an item",
                    "emoji": True
                },
                "options": options,
                "initial_option": initial_option,
                "action_id": f"{action_id}"
            }
        }

    def generate_input_block(self, label, initial_value, action_id, is_multiline=False):
        return {
            "type": "input",
            "element": {
                "type": "plain_text_input",
                "multiline": is_multiline,
                "action_id": action_id,
                "initial_value": initial_value
            },
            "label": {
                "type": "plain_text",
                "text": label,
                "emoji": True
            }
        }
    
    def generate_singlecheckbox_block(self, label, text, action_id, is_checked):
        if text == "": text = " "
        dictionary = {
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": " "
			},
			"accessory": {
				"type": "checkboxes",
				"options": [
					{
						"text": {
							"type": "mrkdwn",
							"text": f"*{label}*"
						},
						"description": {
							"type": "mrkdwn",
							"text": f"{text}"
						},
						"value": "value-0"
					}
				],
				"action_id": f"{action_id}"
			}
		}
        if is_checked:
            dictionary["accessory"]["initial_options"] = [
					{
						"text": {
							"type": "mrkdwn",
							"text": f"*{label}*"
						},
						"description": {
							"type": "mrkdwn",
							"text": f"{text}"
						},
						"value": "value-0"
					}
				]
        return dictionary
    
    def generate_text_block(self, text):
        if text == "": text = " "
        return {
			"type": "section",
			"text": {
				"type": "plain_text",
				"text": text,
				"emoji": True
			}
		}
    
    def generate_button_block(self, label, value, action_id):
        button_block = {
			"type": "actions",
			"elements": []}
        if type(value) == str:
            value = [value]
        if type(action_id) == str:
            action_id = [action_id]
        if len(value) != len(action_id):
            raise Exception(f"Length of value and action_id lists must be equal. Value: {value}, Action_id: {action_id}")
        for i, item in enumerate(value):
            button_block["elements"].append({
					"type": "button",
					"text": {
						"type": "plain_text",
						"text": item.replace("_", " "),
						"emoji": True
					},
					"action_id": action_id[i],
					"value": label + "_" + item
				})
        return button_block

    def generate_slack_blocks(self, debug=False, model_options=None):
    
        # if self.init_values['template']['value'] == 'None':
        #     # shut off the other folders
        #     self.disappear_folder('folder_1')
        #     self.disappear_folder('folder_2')
        # else:
        #     # 

        # # if template editing is disabled
        # # disable all editing settings
        # if not self.init_values['Edit_templates']['value']:
        #     self.disable_template_editing('template')
        # else:
        #     # if template info is visible, then disable it
        #     if self.init_values['template_info']['visible']:
        #         self.init_values['template_info']['visible'] = False

        # if not self.initial_values['template']['value'] in self.template_types:
        #     raise Exception(f"Template {self.initial_values['template']['value']} not found in folder {self.folder_path}")
        # subfolder_labels = self.get_subfolder_labels(self.folder_path)
        block_labels = []
        for key in self.initial_values:
            block_labels.append(key)

        if not model_options:
            model_options = [
                {
                    "text": {
                        "type": "plain_text",
                        "text": "gpt-4-turbo-preview - 128k (latest)",
                        "emoji": True
                    },
                    "value": "gpt-4-turbo-preview"
                },
                {
                    "text": {
                        "type": "plain_text",
                        "text": "gpt-4-0125-preview - 128k tokens",
                        "emoji": True
                    },
                    "value": "gpt-4-0125-preview"
                },
                {
                    "text": {
                        "type": "plain_text",
                        "text": "gpt-4-1106-preview - 128k tokens",
                        "emoji": True
                    },
                    "value": "gpt-4-1106-preview"
                },
                # {
                #     "text": {
                #         "type": "plain_text",
                #         "text": "gpt-4-vision-preview - 128k tokens",
                #         "emoji": True
                #     },
                #     "value": "gpt-4-vision-preview"
                # },
                {
                    "text": {
                        "type": "plain_text",
                        "text": "gpt-4 - 8k token limit",
                        "emoji": True
                    },
                    "value": "gpt-4"
                },
                {
                    "text": {
                        "type": "plain_text",
                        "text": "gpt-4-0613 - 8k token limit",
                        "emoji": True
                    },
                    "value": "gpt-4-0613"
                },
                # {
                #     "text": {
                #         "type": "plain_text",
                #         "text": "gpt-4-32k - 32k token limit",
                #         "emoji": True
                #     },
                #     "value": "gpt-4-32k"
                # },
                {
                    "text": {
                        "type": "plain_text",
                        "text": "gpt-3.5-turbo-16k - 16k tokens",
                        "emoji": True
                    },
                    "value": "gpt-3.5-turbo-16k"
                },
                {
                    "text": {
                        "type": "plain_text",
                        "text": "gpt-3.5-turbo - 4k token limit",
                        "emoji": True
                    },
                    "value": "gpt-3.5-turbo"
                },
                {
                    "text": {
                        "type": "plain_text",
                        "text": "gpt-3.5-turbo-0125 - 16k token limit",
                        "emoji": True
                    },
                    "value": "gpt-3.5-turbo-0125"
                },
            ]
        else:
            model_options = model_options
        blocks = []
        for label in block_labels:
            spaced_label = self.initial_values[label]['block_text']
            # spaced_label = label.replace("_", " ")
            block = None
            if self.initial_values[label]['visable']:
                if self.initial_values[label]['block_type'] == 'checkbox':
                    block = self.generate_singlecheckbox_block(spaced_label, " ", label, self.initial_values[label]['value'])
            
                elif self.initial_values[label]['block_type'] == 'select-folder':
                    key = self.initial_values[label]["level"]
                elif self.initial_values[label]['block_type'] == 'select':
                    block = self.generate_dropdown_block(spaced_label, self.initial_values[label]['value'], label, model_options)
                elif self.initial_values[label]['block_type'] == 'input':
                    # spaced_label = self.initial_values[label]['block_text']
                    block = self.generate_input_block(spaced_label, self.initial_values[label]['value'], label, False)
                elif self.initial_values[label]['block_type'] == 'input-multiline':
                    block = self.generate_input_block(spaced_label, self.initial_values[label]['value'], label, True)
                    # print("block", block)
                elif self.initial_values[label]['block_type'] == 'text':
                    block = self.generate_text_block(self.initial_values[label]['value'])
                elif self.initial_values[label]['block_type'] == 'button':
                    block = self.generate_button_block(spaced_label, self.initial_values[label]['value'], self.initial_values[label]['action_id'])
            if block:
                blocks.append(block)
        # import code; code.interact(local=dict(globals(), **locals()))
        return {"blocks": blocks}

    def dropdown_editor(self, name):
        return {name: {
            f"{name}": {"visable": False, "value": "None", "form_search_key": "selected_option/text/text", "block_type": "select-folder", "action_id": f"{name}"},
            f"{name}_buttons": {"visable": False, "value": ["create_new", "prompt", "delete", "rename", "info"], "form_search_key": "selected_options", "block_type": "button", "action_id": [f"{name}_button_create_new", f"{name}_button_prompt", f"{name}_button_delete", f"{name}_button_rename", f"{name}_button_info"]},
            f"{name}_info": {"visable": False, "value": " ", "form_search_key": "selected_option/text/text", "block_type": "text", "action_id": None},
            f"{name}_rename": {"visable": False, "value": f"{name}_rename", "form_search_key": "value", "block_type": "input", "action_id": f"{name}_rename"},
            f"new_{name}_name": {"visable": False, "value": f"new_{name}_name", "form_search_key": "value", "block_type": "input", "action_id": f"new_{name}_name"},
            f"start/copy_from_{name}": {"visable": False, "value": "None", "form_search_key": "selected_option/text/text", "block_type": "select-folder", "action_id": f"start/copy_from_{name}"},
            f"{name}_prompt": {"visable": False, "value": "core prompt goes here", "form_search_key": "value", "block_type": "input-multiline", "action_id": f"{name}_prompt"},
            f"{name}_save_button": {"visable": False, "value": "Save_changes", "form_search_key": "selected_options", "block_type": "button", "action_id": f"{name}_button_Save_changes"},
        }}









class SlackBlockGenerator:
    def __init__(self, temp_folder, default_template_path, initial_values):
        print("temp_folder: ", temp_folder)
        print("default_template_path: ", default_template_path)
        # TODO: largely eliminate the need for default_template_path
        self.folder_path = default_template_path.split(os.sep)[0]
        # make sure that default_template_path is at least 2 levels deep
        # default_depth = len(default_template_path.split(os.sep))
        # # raise Exception if less than 2 levels deep
        # if default_depth < 2:
        #     raise Exception("default_template_path must be at least 2 levels deep")
        if self.folder_path == temp_folder.split(os.sep)[-1]:
            # combine default_template_path path segments, excluding the first one
            # self.temp_folder_path_segments_minus_1 = os.sep.join(temp_folder.split(os.sep)[:-1] + default_template_path.split(os.sep))
            self.temp_folder_path_segments_minus_1 = str(Path(temp_folder).parent)  # os.sep.join(temp_folder.split(os.sep)[:-1])
        else:
            self.temp_folder_path_segments_minus_1 = "."
        self.level_to_path = {}
        temp_path = ""
        for i, segment in enumerate(default_template_path.split(os.sep)):
            temp_path += '/' + segment
            self.level_to_path[i] = self.temp_folder_path_segments_minus_1 + temp_path

        # print(self.level_to_path)

        
        # self.folder_1_path = default_template_path.rsplit('/', 2)[0]
        # self.folder_2_path = default_template_path.rsplit('/', 1)[0]
        # self.folder_3_path = default_template_path
        # self.level_to_path = {
        #     0: self.temp_folder_path_segments_minus_1 + "/" + self.folder_path,
        #     1: self.temp_folder_path_segments_minus_1 + "/" + self.folder_1_path,
        #     2: self.temp_folder_path_segments_minus_1 + "/" + self.folder_2_path,
        #     3: self.temp_folder_path_segments_minus_1 + "/" + self.folder_3_path
        # }
        self.initial_values = initial_values

    def get_subfolders(self, folder_path):
        # get a list of the names of the folders in the folder_path (only the first level)
        # below is the long way to write: [d for d in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, d)) and d != "vars"]
        subfolders = []
        for d in os.listdir(folder_path):
            if os.path.isdir(os.path.join(folder_path, d)) and d != "vars":
                subfolders.append(d)
        return subfolders

    
    def generate_dropdown_block(self, parent_folder, initial_value, action_id, options):        
        initial_option = next((opt for opt in options if opt["value"] == initial_value), None)
        if not initial_option and options:
            initial_option = options[0]

        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": parent_folder
            },
            "accessory": {
                "type": "static_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Select an item",
                    "emoji": True
                },
                "options": options,
                "initial_option": initial_option,
                "action_id": f"{action_id}"
            }
        }

    def generate_input_block(self, label, initial_value, action_id, is_multiline=False):
        return {
            "type": "input",
            "element": {
                "type": "plain_text_input",
                "multiline": is_multiline,
                "action_id": action_id,
                "initial_value": initial_value
            },
            "label": {
                "type": "plain_text",
                "text": label,
                "emoji": True
            }
        }

    def traverse_directory(self, parent_path, current_path=''):
        options = []

        for item in os.listdir(parent_path):
            item_path = os.path.join(parent_path, item)
            if os.path.isdir(item_path):
                subdirs = [d for d in os.listdir(item_path) if os.path.isdir(os.path.join(item_path, d))]
                if not subdirs:  # Check if the item has no subfolders
                    child_path = os.path.join(current_path, item)
                    options.append(child_path)
                else:
                    child_options = self.traverse_directory(item_path, os.path.join(current_path, item))
                    options.extend(child_options)
        return options

    def get_options(self, parent_folder, root, dirs):
        options = self.traverse_directory(root)
        folder_options = []
        
        for option in options:
            option_path = os.path.join(root, option)
            if os.path.isdir(option_path) and os.listdir(option_path):
                folder_options.append({
                    "text": {
                        "type": "plain_text",
                        "text": '/'.join(option.split(os.sep)),
                        "emoji": True
                    },
                    "value": '/'.join(option.split(os.sep))
                })
        return folder_options

    def get_subfolder_labels(self, folder_path):
        return [d for d in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, d))]
    
    def generate_singlecheckbox_block(self, label, text, action_id, is_checked):
        if text == "": text = " "
        dictionary = {
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": " "
			},
			"accessory": {
				"type": "checkboxes",
				"options": [
					{
						"text": {
							"type": "mrkdwn",
							"text": f"*{label}*"
						},
						"description": {
							"type": "mrkdwn",
							"text": f"{text}"
						},
						"value": "value-0"
					}
				],
				"action_id": f"{action_id}"
			}
		}
        if is_checked:
            dictionary["accessory"]["initial_options"] = [
					{
						"text": {
							"type": "mrkdwn",
							"text": f"*{label}*"
						},
						"description": {
							"type": "mrkdwn",
							"text": f"{text}"
						},
						"value": "value-0"
					}
				]
        return dictionary
    
    def generate_text_block(self, text):
        if text == "": text = " "
        return {
			"type": "section",
			"text": {
				"type": "plain_text",
				"text": text,
				"emoji": True
			}
		}
    
    def generate_button_block(self, label, value, action_id):
        button_block = {
			"type": "actions",
			"elements": []}
        if type(value) == str:
            value = [value]
        if type(action_id) == str:
            action_id = [action_id]
        if len(value) != len(action_id):
            raise Exception(f"Length of value and action_id lists must be equal. Value: {value}, Action_id: {action_id}")
        for i, item in enumerate(value):
            button_block["elements"].append({
					"type": "button",
					"text": {
						"type": "plain_text",
						"text": item.replace("_", " "),
						"emoji": True
					},
					"action_id": action_id[i],
					"value": label + "_" + item
				})
        return button_block

    def generate_slack_blocks(self, debug=False, model_options=None):
    
        # if self.init_values['template']['value'] == 'None':
        #     # shut off the other folders
        #     self.disappear_folder('folder_1')
        #     self.disappear_folder('folder_2')
        # else:
        #     # 

        # # if template editing is disabled
        # # disable all editing settings
        # if not self.init_values['Edit_templates']['value']:
        #     self.disable_template_editing('template')
        # else:
        #     # if template info is visible, then disable it
        #     if self.init_values['template_info']['visible']:
        #         self.init_values['template_info']['visible'] = False

        # if not self.initial_values['template']['value'] in self.template_types:
        #     raise Exception(f"Template {self.initial_values['template']['value']} not found in folder {self.folder_path}")
        # subfolder_labels = self.get_subfolder_labels(self.folder_path)
        block_labels = []
        for key in self.initial_values:
            block_labels.append(key)


        if not model_options:
            model_options = [
                {
                    "text": {
                        "type": "plain_text",
                        "text": "gpt-4-turbo-preview - 128k (latest)",
                        "emoji": True
                    },
                    "value": "gpt-4-turbo-preview"
                },
                {
                    "text": {
                        "type": "plain_text",
                        "text": "gpt-4-0125-preview - 128k tokens",
                        "emoji": True
                    },
                    "value": "gpt-4-0125-preview"
                },
                {
                    "text": {
                        "type": "plain_text",
                        "text": "gpt-4-1106-preview - 128k tokens",
                        "emoji": True
                    },
                    "value": "gpt-4-1106-preview"
                },
                # {
                #     "text": {
                #         "type": "plain_text",
                #         "text": "gpt-4-vision-preview - 128k tokens",
                #         "emoji": True
                #     },
                #     "value": "gpt-4-vision-preview"
                # },
                {
                    "text": {
                        "type": "plain_text",
                        "text": "gpt-4 - 8k token limit",
                        "emoji": True
                    },
                    "value": "gpt-4"
                },
                {
                    "text": {
                        "type": "plain_text",
                        "text": "gpt-4-0613 - 8k token limit",
                        "emoji": True
                    },
                    "value": "gpt-4-0613"
                },
                # {
                #     "text": {
                #         "type": "plain_text",
                #         "text": "gpt-4-32k - 32k token limit",
                #         "emoji": True
                #     },
                #     "value": "gpt-4-32k"
                # },
                {
                    "text": {
                        "type": "plain_text",
                        "text": "gpt-3.5-turbo-16k - 16k tokens",
                        "emoji": True
                    },
                    "value": "gpt-3.5-turbo-16k"
                },
                {
                    "text": {
                        "type": "plain_text",
                        "text": "gpt-3.5-turbo - 4k token limit",
                        "emoji": True
                    },
                    "value": "gpt-3.5-turbo"
                },
                {
                    "text": {
                        "type": "plain_text",
                        "text": "gpt-3.5-turbo-0125 - 16k token limit",
                        "emoji": True
                    },
                    "value": "gpt-3.5-turbo-0125"
                },
            ]
        else:
            model_options = model_options
        using_a_template = True
        if self.initial_values['template']['value'] == 'None':
            using_a_template = False
        blocks = []
        for label in block_labels:
            spaced_label = self.initial_values[label]['block_text']
            # spaced_label = label.replace("_", " ")
            block = None
            if self.initial_values[label]['visable']:
                if self.initial_values[label]['block_type'] == 'checkbox':
                    block = self.generate_singlecheckbox_block(spaced_label, " ", label, self.initial_values[label]['value'])
            
                elif self.initial_values[label]['block_type'] == 'select-folder':
                    key = self.initial_values[label]["level"]

                    special_case_variables = (not using_a_template and label == 'variables' and \
                                                self.initial_values['Edit_templates']['value'])
                    # disable the dropdown if label is not template
                    if label == 'template' or using_a_template == True \
                        or special_case_variables:
                        # if key error, then the folder is not visable/ set to 'None'
                        keyerror = False
                        try:
                            path_to_subfolder = self.level_to_path[key]
                        except KeyError:
                            keyerror = True
                        if keyerror or special_case_variables:
                            subfolders = ["None"]
                        else:
                            subfolders = self.get_subfolders(path_to_subfolder)
                        if label == "variables":
                            path = self.level_to_path[1] + "/vars"
                            # check that the path exists
                            if not os.path.exists(path) or special_case_variables:
                                subfolders = ["None"]
                            else:
                                def get_variables(path):
                                    # get all the txt file names in the vars folder(without the .txt)
                                    variables = [f.split(".")[0] for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
                                    return variables
                                variables = get_variables(path)
                                if len(variables) == 0 and self.initial_values[label]['value'] == "None":
                                    subfolders = ["None"]
                                elif len(variables) == 0:
                                    subfolders = ["None"]
                                    # set the value to None
                                elif self.initial_values[label]['value'] == "None" and len(variables) > 0:
                                    subfolders = variables
                                else:
                                    subfolders = variables
                        # the front of the list is the default value of the dropdown
                        # put self.initial_values[label]['value'] at the front of the list if it is not "None" and is in the list
                        if self.initial_values[label]['value'] != "None" and self.initial_values[label]['value'] in subfolders:
                            subfolders.remove(self.initial_values[label]['value'])
                            subfolders = [self.initial_values[label]['value']] + subfolders
                        if label == "template":
                            if subfolders != ["None"]:
                                subfolders = subfolders + ["None"]
                        if subfolders == []:
                            subfolders = ["None"]
                        options = []
                        for folder in subfolders:
                            folder = folder.replace("_", " ")
                            options.append({
                                    "text": {
                                        "type": "plain_text",
                                        "text": folder,
                                        "emoji": True
                                    },
                                    "value": folder
                                })
                        block = self.generate_dropdown_block(self.initial_values[label]['block_text'], self.initial_values[label]['value'], label, options)
                        if debug:
                            pass
                elif self.initial_values[label]['block_type'] == 'select':
                    block = self.generate_dropdown_block(spaced_label, self.initial_values[label]['value'], label, model_options)
                elif self.initial_values[label]['block_type'] == 'input':
                    # spaced_label = self.initial_values[label]['block_text']
                    block = self.generate_input_block(spaced_label, self.initial_values[label]['value'], label, False)
                elif self.initial_values[label]['block_type'] == 'input-multiline':
                    block = self.generate_input_block(spaced_label, self.initial_values[label]['value'], label, True)
                    # print("block", block)
                elif self.initial_values[label]['block_type'] == 'text':
                    block = self.generate_text_block(self.initial_values[label]['value'])
                elif self.initial_values[label]['block_type'] == 'button':
                    block = self.generate_button_block(spaced_label, self.initial_values[label]['value'], self.initial_values[label]['action_id'])
            if block:
                blocks.append(block)
        # import code; code.interact(local=dict(globals(), **locals()))
        return {"blocks": blocks}
    
    def disappear_folder(self, keyword):
        # if keyword is in any of self.initial_values keys, set visible to False
        for key in self.initial_values:
            if keyword in key or keyword.lower() in key:
                self.initial_values[key]['visible'] = False

    def dropdown_editor(self, name):
        return {name: {
            f"{name}": {"visable": False, "value": "None", "form_search_key": "selected_option/text/text", "block_type": "select-folder", "action_id": f"{name}"},
            f"{name}_buttons": {"visable": False, "value": ["create_new", "prompt", "delete", "rename", "info"], "form_search_key": "selected_options", "block_type": "button", "action_id": [f"{name}_button_create_new", f"{name}_button_prompt", f"{name}_button_delete", f"{name}_button_rename", f"{name}_button_info"]},
            f"{name}_info": {"visable": False, "value": " ", "form_search_key": "selected_option/text/text", "block_type": "text", "action_id": None},
            f"{name}_rename": {"visable": False, "value": f"{name}_rename", "form_search_key": "value", "block_type": "input", "action_id": f"{name}_rename"},
            f"new_{name}_name": {"visable": False, "value": f"new_{name}_name", "form_search_key": "value", "block_type": "input", "action_id": f"new_{name}_name"},
            f"start/copy_from_{name}": {"visable": False, "value": "None", "form_search_key": "selected_option/text/text", "block_type": "select-folder", "action_id": f"start/copy_from_{name}"},
            f"{name}_prompt": {"visable": False, "value": "core prompt goes here", "form_search_key": "value", "block_type": "input-multiline", "action_id": f"{name}_prompt"},
            f"{name}_save_button": {"visable": False, "value": "Save_changes", "form_search_key": "selected_options", "block_type": "button", "action_id": f"{name}_button_Save_changes"},
        }}


if __name__ == "__main__":
    default_template_trace = "templates/newsletter/Pipe_Hitter_Foundation/fundraising"
    # default_template_path = "templates/pirate_speak"
    path_to_temp_template_folder = "./templates"
    default_template_trace = "templates/pirate_speak"

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
        "sf_template_name_id": {"block_text": "SF Template Name Id (assists prompt tracing)", "visable": True, "value": "AVC Oct 2023 F3", "form_search_key": "value", "block_type": "input", "action_id": "job_name"},
        "Edit_templates": {"block_text": "Edit", "visable": False, "value": False, "form_search_key": "selected_options", "block_type": "checkbox", "action_id": "Edit_templates"}, 
        
        "template": {"block_text": "client", "level": 0, "visable": False, "value": "None", "form_search_key": "selected_option/text/text", "block_type": "select-folder", "action_id": "template"}, 
        "template_buttons": {"block_text": " ", "level": 0, "visable": False, "value": template_button_values, "form_search_key": "selected_options", "block_type": "button", "action_id": folder_buttons["template"]},
        "template_info": {"block_text": " ", "level": 0, "visable": False, "value": " ", "form_search_key": "selected_option/text/text", "block_type": "text", "action_id": None}, 
        "template_rename": {"block_text": "rename", "level": 0, "visable": False, "value": "template_rename", "form_search_key": "value", "block_type": "input", "action_id": "template_rename"}, 
        "new_template_name": {"block_text": "new client's name", "level": 0, "visable": False, "value": " ", "form_search_key": "value", "block_type": "input", "action_id": "new_template_name"}, 
        "start/copy_from_template": {"block_text": "* _*optional*_ * - start with a copy of", "level": 0, "visable": False, "value": "None", "form_search_key": "selected_option/text/text", "block_type": "select-folder", "action_id": "start/copy_from_template"}, 
        "template_prompt": {"block_text": "prompt", "level": 0, "visable": False, "value": "core prompt goes here", "form_search_key": "value", "block_type": "input-multiline", "action_id": "template_prompt"},
        "template_save_button": {"block_text": "Save changes", "level": 0, "visable": False, "value": "Save_changes", "form_search_key": "selected_options", "block_type": "button", "action_id": "template_button_Save_changes"},

        "folder_1": {"block_text": "email type", "level": 1, "visable": False, "value": "None", "form_search_key": "selected_option/text/text", "block_type": "select-folder", "action_id": "folder_1"},
        "folder_1_buttons": {"block_text": " ", "level": 1, "visable": False, "value": button_values, "form_search_key": "selected_options", "block_type": "button", "action_id": folder_buttons["folder_1"]},
        "folder_1_info": {"block_text": " ", "level": 1, "visable": False, "value": " ", "form_search_key": "selected_option/text/text", "block_type": "text", "action_id": None},
        "folder_1_rename": {"block_text": "rename", "level": 1, "visable": False, "value": "folder_1_rename", "form_search_key": "value", "block_type": "input", "action_id": "folder_1_rename"},
        "new_folder_1_name": {"block_text": "new email type's name", "level": 1, "visable": False, "value": " ", "form_search_key": "value", "block_type": "input", "action_id": "new_folder_1_name"},
        "start/copy_from_folder_1": {"block_text": "* _*optional*_ * - start with a copy of", "level": 1, "visable": False, "value": "None", "form_search_key": "selected_option/text/text", "block_type": "select-folder", "action_id": "start/copy_from_folder_1"},
        "folder_1_prompt": {"block_text": "prompt", "level": 1, "visable": False, "value": "core prompt goes here", "form_search_key": "value", "block_type": "input-multiline", "action_id": "folder_1_prompt"},
        "folder_1_save_button": {"block_text": "Save changes", "level": 1, "visable": False, "value": "Save_changes", "form_search_key": "selected_options", "block_type": "button", "action_id": "folder_1_button_Save_changes"},

        "folder_2": {"block_text": "email template", "level": 2, "visable": False, "value": "None", "form_search_key": "selected_option/text/text", "block_type": "select-folder", "action_id": "folder_2"},
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
                
        
        "prompt_queue_checkbox": {"block_text": "Oscar PromptChain (yaml format)", "visable": True, "value": True, "form_search_key": "selected_options", "block_type": "checkbox", "action_id": "prompt_queue_checkbox"}, 

        "writing_instructions": {"block_text": "Prompt", "visable": True, "value": "What color is the sky?", "form_search_key": "value", "block_type": "input-multiline", "action_id": "writing_instructions"},        
        "preview_checkbox": {"block_text": "preview prompt", "visable": False, "value": False, "form_search_key": "selected_options", "block_type": "checkbox", "action_id": "preview_checkbox"},
        "preview": {"block_text": "prompt preview", "visable": False, "value": " ", "form_search_key": "selected_option/text/text", "block_type": "text", "action_id": "preview_0"},
        "model": {"block_text": "model", "visable": True, "value": "gpt-4-0613", "form_search_key": "selected_option/text/text", "block_type": "select", "action_id": "model"},
        "temperature": {"block_text": "temperature", "visable": True, "value": "0.2", "form_search_key": "value", "block_type": "input", "action_id": "temperature"}, 
        "samples": {"block_text": "samples", "visable": True, "value": "2", "form_search_key": "value", "block_type": "input", "action_id": "samples"}
    }
    generator = SlackBlockGenerator(path_to_temp_template_folder, default_template_trace, init_values)
    result = generator.generate_slack_blocks()
    print(json.dumps(result, indent=4, sort_keys=True))
