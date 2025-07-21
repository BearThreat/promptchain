# python3 bert_5class_openrate_inference.py "test string title"
# output should be: 4.74122679233551
# import torch
# import time
import sys
from transformers import AutoTokenizer, pipeline, AutoModelForSequenceClassification, logging, BertTokenizerFast
import torch
import decimal
import os
import pickle
# import pandas as pd


def round_up(x, place=0):
    context = decimal.getcontext()
    # get the original setting so we can put it back when we're done
    original_rounding = context.rounding
    # change context to act like ceil()
    context.rounding = decimal.ROUND_CEILING

    rounded = round(decimal.Decimal(str(x)), place)
    context.rounding = original_rounding
    return float(rounded)


def cleanText(dirty_text, model_tokenizer, model_max_token_length):
    body = str(dirty_text)
    body = body.encode("ascii", "ignore")
    body = body.decode()
    body = model_tokenizer.encode(body)
    # cut body down to the model's max_token_length
    body = body[:model_max_token_length]
    # detokenize body
    cleaned_text = model_tokenizer.decode(body, skip_special_tokens=True)
    return cleaned_text


def inference(text, model, tokenizer, quick_float_format=True):
    # keep this or you will get a very long and irrelevant huggingface warning message
    logging.set_verbosity_error()
    text = cleanText(text, tokenizer, 512)

    # builds a model_type kind of model with random weights
    # model = AutoModelForSequenceClassification.from_pretrained(path, num_labels=num_labels)

    # loads model shape with the trained weights from path
    # if left out the weights will be random (and this inference will output nonsense)
    # model.load_state_dict(
    #     torch.load(path, map_location=torch.device('cpu')))  # must use cpu if machine has no gpu
    if torch.cuda.is_available():
        device = torch.device("cuda")
        device = 0
    else:
        device = torch.device("cpu")
    # print(text)
    # print(device)

    classifier = pipeline('sentiment-analysis', model=model, tokenizer=tokenizer, device=device, top_k=None)  # top_k=5)
    out = classifier(text)
    out = [sorted(out[0], key=lambda k: k['label'])]
    #print(out)
    if quick_float_format:
        return quickFloatFormat(out)
    else:
        return out


def quickFloatFormat(model_inference_result):
    """[[{'label': 'LABEL_3', 'score': 0.378303587436676}, {'label': 'LABEL_4', 'score': 0.3302166759967804}, {'label': 'LABEL_2', 'score': 0.1371358036994934}, {'label': 'LABEL_1', 'score': 0.09616061300039291}, {'label': 'LABEL_0', 'score': 0.05818326771259308}]]"""
    probabilities_for_each_range_of_opens = []
    for dic_ in model_inference_result[0]:
        probabilities_for_each_range_of_opens.append(float(dic_['score']))

    # print("probabilities_for_each_range_of_opens", probabilities_for_each_range_of_opens)

    # finds the most likely class
    # largest number is most likely
    # print(max(probabilities_for_each_range_of_opens))
    index_of_highest_prediction = probabilities_for_each_range_of_opens.index(
        max(probabilities_for_each_range_of_opens))
    # print("index_of_highest_prediction: " + str(index_of_highest_prediction))

    output__ = probabilities_for_each_range_of_opens[index_of_highest_prediction] + index_of_highest_prediction
    # output integer part of float is the model's class number
    # ouput decimal part is the model's certainty of the class
    # note: certainty will always be greater than a fraction of the total buckets
    # (5 buckets/classification options means that the minimum value of the winning certainty is 100% / 5 = 20.00001%
    return output__


def buildAutoModelForSequenceClassification(model_name_str):
    # loads model shape with the trained weights from path
    if model_name_str[-1] == '/':
        raise Exception("Invalid string format.")

    if "/" in model_name_str:
        model_name_str = model_name_str.split("/")[-1]

    path = model_name_str + "/"
    num_label = int(model_name_str.split("__")[1])
    return AutoModelForSequenceClassification.from_pretrained(path, num_labels=num_label)


def getBertFastTokenizer(model_name_str):
    return BertTokenizerFast.from_pretrained(model_name_str.split("__")[0])


def getAutoTokenizer(model_name_str):
    return AutoTokenizer.from_pretrained(model_name_str.split("__")[0])


def setup_bert(path_to_folder_with_config_and_model_bin_file):
    # look at last part of path to get model name.
    # Then look at the number after the model name to get the number of labels
    if path_to_folder_with_config_and_model_bin_file is None:
        raise Exception("Model not found.")

    # get the last part of the path
    model_fullname_str = path_to_folder_with_config_and_model_bin_file.split("/")[-1]

    # Check that model_path contains at least 3 "__"
    if model_fullname_str.count("__") < 3 or not int(model_fullname_str.split("__")[1]) > 0:
        raise Exception("Invalid model path.")

    # get model type
    model_type = model_fullname_str.split("__")[0]

    # get the number of labels
    num_labels = int(model_fullname_str.split("__")[1])

    # get name of model (it's also the name of the folder)
    # model_name_str = path_to_folder_with_config_and_model_bin_file.split("/")[-1]
    # model_load_time = time.time()
    model = AutoModelForSequenceClassification.from_pretrained(path_to_folder_with_config_and_model_bin_file,
                                                               num_labels=num_labels, local_files_only=True)
    # model_load_time = time.time() - model_load_time
    # tokenizer_load_time = time.time()
    tokenizer = BertTokenizerFast.from_pretrained(model_type)
    # tokenizer = AutoTokenizer.from_pretrained(model_type)

    # tokenizer_load_time = time.time() - tokenizer_load_time
    # print("Model loaded in: " + str(model_load_time) + " seconds.")
    # print("Tokenizer loaded in: " + str(tokenizer_load_time) + " seconds.")
    return model, tokenizer


def find_most_recent_ai_model(ai_model_folder_start_name):
    """
    Finds the most recent model folder. Searches up 2 layers. First look in the current dir and then look in all local folders in current dir.
    param: ai_model_folder_start_name: string of start name of the folder that contains the model
    return: the relative path to the most recent model folder.
    """
    # First look in the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    local_simplet5_folders = find_folders(current_dir, ai_model_folder_start_name)
    if len(local_simplet5_folders) > 0:
        return str(max(local_simplet5_folders, key=os.path.getctime))

    # if there are no folders in the current directory starting with ai_model_folder_start_name (e.g. bert-based-uncased, t5), look in the local folders
    local_folder_list = []
    if len(local_simplet5_folders) == 0:
        for root, dirs, files in os.walk("."):
            for folder in dirs:
                if not folder.startswith('.'):
                    # don't look in directories that start with a "." (like .aws-sam)
                    folder_names = root.split('/')[1:]
                    folder_name_start_with_period = []
                    for folder_name in folder_names:
                        if folder_name[0] == '.':
                            folder_name_start_with_period.append(True)
                        else:
                            folder_name_start_with_period.append(False)
                    if folder.startswith(ai_model_folder_start_name) and \
                            not any(folder_name_start_with_period) and \
                            is_file_at_path(root + '/' + folder, 'config.json') and \
                            is_file_at_path(root + '/' + folder, 'model.bin'):
                        # append the path to the folder to the list
                        local_folder_list.append(os.path.join(root, folder))
        print("Found the following local folders:")
        print(local_folder_list)
        if len(local_folder_list) > 0:
            print(f"Choosing the most recent folder: {max(local_folder_list, key=os.path.getctime)}")
            return str(max(local_folder_list, key=os.path.getctime))
        else:
            raise Exception(f"No {ai_model_folder_start_name} model found in current dir or directly local folders.")


def find_folders(path_to_search_dir, folder_name):
    """
    Finds all the folders in the current directory that start with 'simplet5'.
    param: None
    return: list of all folders that start with 'simplet5'
    """
    folder_paths = []
    # find all possible simplet5 folders in the directory
    for folder in os.listdir(path_to_search_dir):
        # find the most recent folder
        if folder.startswith(folder_name):
            folder_paths.append(path_to_search_dir + "/" + folder)

    return folder_paths


def is_file_at_path(path_to_search_dir, file_name):
    """
    Checks if the directory contains a file with the given name.
    param: path_to_search_dir: the directory to search
    param: file_name: the name of the file to search for
    return: True if the file is found, False if not
    """
    for file in os.listdir(path_to_search_dir):
        if file == file_name or file.endswith(file_name):
            return True
    return False


# Press the green button in the gutter to run the script. # why did I write this?
if __name__ == '__main__':
    # subjectline_file = sys.argv[1]
    # # throw error if subjectline_file is not a txt file
    # if not subjectline_file.endswith(".txt"):
    #     raise Exception("Subjectline file must be a txt file.")
    # start_time = time.time()
    bert_model, bert_tokenizer = setup_bert(find_most_recent_ai_model("bert-base-uncased"))
    pickle.dump(bert_model, open("bert-model", 'wb'))
    pickle.dump(bert_tokenizer, open("bert-tokenizer", 'wb'))
    this_script_path = os.path.dirname(os.path.abspath(__file__))
    bert_model = pickle.load(open(f"{this_script_path}/bert-model", 'rb'))
    bert_tokenizer = pickle.load(open(f"{this_script_path}/bert-tokenizer", 'rb'))
    # start_time = time.time()
    # infer = inference(string, bert_model, bert_tokenizer)
    # print(infer)
    # print("Execution time: %s seconds" % (time.time() - start_time))
    import time
    t0 = time.time()
    val = inference("test line to grade and time", bert_model, bert_tokenizer, quick_float_format=True)
    print(val)
    print("Execution time: %s seconds" % (time.time() - t0))

    # with open(f"{subjectline_file}", "r") as f:
    #     lines = f.readlines()
    #     # create an empty dataframe
    #     df = pd.DataFrame(columns=['text', 'prediction'])
    #     # get inference for each line
    #     for line in lines:
    #         line = line.strip()
    #         infer = inference(line, bert_model, bert_tokenizer, quick_float_format=True)

    #         # append the line and the inference to a dataframe
    #         df = df.append({'text': line, 'prediction': infer}, ignore_index=True)
    #         # print(df)

    # print(df)
    # # sort df by inference
    # df = df.sort_values(by=['prediction'], ascending=False)
    # # only keep the high quality subject lines
    # # this is weird because quickFloatFormat is incomplete
    # print(df)
    # df_top_class = df[(4.2 < df['prediction']) & (df['prediction'] < 5)]
    # print(df_top_class)
    # df_2nd_highest_class = df[(3.4 < df['prediction']) & (df['prediction'] < 4)]
    # print(df_2nd_highest_class)
    # df = df_top_class.append(df_2nd_highest_class)
    # print(df)

    # # # print every line in the now sorted dataframe in reverse order
    # # idx = 0
    # # for index, row in df.iterrows():
    # #     # if the text doesn't contain the word "kindergarten"
    # #     if "kindergarten" not in row['text']:
    # #         print(f"{idx}\t", row['prediction'], "\t", row['text'])
    # #         idx += 1
    # filename = ''
    # if len(subjectline_file.split('/')) > 1:
    #     filename = subjectline_file.split('/')[-1]
    # else:
    #     filename = subjectline_file

    # # write the now sorted text column into a text file
    # with open(f"open_rate_sort_{filename}", "w") as f:
    #     for index, row in df.iterrows():
    #         f.write(row['text'] + "\n")
    #         print(f"{index}\t", row['prediction'], "   \t\t", row['text'])

