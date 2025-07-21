import tiktoken
import fire
import os


def simple_tok_len(model, text: str) -> int:
        return len(tiktoken.encoding_for_model(model).encode(text))

def tok_len(text: str, models=None) -> int:
    # if text is a file, read it
    if os.path.exists(text):
        with open(text, "r") as f:
            text = f.read()
    """
    print(text[-10:])
    if models is not None:
        print(models[-10:])
    models = ["gpt-3.5-turbo", "gpt-4"]
    for model in models:
        token_count = simple_tok_len(model, text)
        print(model, "token length =", token_count)"""
    
    if models is None:
        models = ["gpt-3.5-turbo", "gpt-4"]
        for model in models:
            token_count = simple_tok_len(model, text)
            print(model, "token length =", token_count)
    elif isinstance(models, list) and isinstance(models[0], str):
        for model in models:
            token_count = simple_tok_len(models, text)
            print(models, "token length =", token_count)
    else:
        raise ValueError("models must be a list or None type")

# open token_count.txt and count the number of tokens in the file
with open("token_count.txt", "r") as f:
    text = f.read()
    tok_len(text)

# # turn the above into a command line tool
# if __name__ == "__main__":
#     fire.Fire(tok_len)

