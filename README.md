# Savant: An AI-Powered Slack Workflow Automation Platform

Savant is a sophisticated, AI-driven Slack bot designed to enhance marketing and copywriting workflows. It integrates with multiple large language models (LLMs) to automate complex creative tasks, streamline content generation, and dramatically boost productivity, all within the familiar Slack interface.

## Project Philosophy

This project was built with a few key principles in mind:

*   **Pragmatism over Hype:** The focus is on building robust, reliable tools that solve real-world problems. This is why, for example, the BERT model was deployed on a CPU-based multiprocessing solution. While a GPU would have been faster, the CPU-based solution was more stable, easier to deploy, and more than fast enough for the task.
*   **Empowering Non-Technical Users:** The custom DSL for prompt chaining was designed to be simple enough for non-technical users to create and modify complex creative workflows without having to write any code.
*   **Flexibility and Future-Proofing:** The model-agnostic approach, using API aggregators like OpenRouter, allows for rapid A/B testing of new models as they are released, ensuring that Savant can always use the best tool for the job.

## Core Features & Technical Deep Dive

This repository showcases the core logic of the Savant platform, demonstrating advanced concepts in AI engineering, asynchronous programming, and system architecture.

### 1. AI-Powered Slack Automation & Creative Partnership

Savant transforms a simple classification analysis tool into a powerful creative partner for marketing teams. It breaks down complex writing tasks into sequential, manageable stages, guiding copywriters through the creative process.

-   **Implementation:** The core of the Slack integration can be found in [`async_server.py`](./async_server.py), which handles the main application loop, and [`slack_custom_actions.py`](./slack_custom_actions.py), which manages custom interactions and commands within Slack.

### 2. Custom DAG-based Prompt Chaining Engine

At the heart of Savant is a custom-built Directed Acyclic Graph (DAG) execution engine. This system parses a domain-specific Markdown format (`promptchain.md`) to define complex prompt dependencies, allowing the output of one LLM call to be used as a variable input for subsequent calls.

#### The Promptchain Markdown Parser

The parser, located in `promptchain_parser.py`, is the cornerstone of this system. It was designed with a critical goal: to create a Domain-Specific Language (DSL) that is both **human-readable** and **robustly parsable**. This allows non-technical users, like copywriters, to design, modify, and execute complex, multi-step creative workflows without writing a single line of code.

**Key Design Choices & Reasoning:**

*   **Markdown as a DSL:** Markdown was chosen for its simplicity and readability. The use of `###` for section separation and `-` for key-value pairs is intuitive and requires no special training. This lowers the barrier to entry for creating sophisticated prompt chains.
*   **Simple Variable Substitution:** The `[[variable_name]]` syntax is intentionally simple and visually distinct. The parser enforces a "varized" format (lowercase, underscores for spaces) to prevent ambiguity and ensure reliable substitution. This design avoids complex templating languages that would increase the learning curve.
*   **DAG-based Execution & Scheduling:** The parser doesn't just read the file; it builds a Directed Acyclic Graph representing the dependencies between prompts. The `find_runnable_steps` function acts as a scheduler, identifying all steps whose variable dependencies have been met. This is crucial for performance, as it allows independent prompt steps to be executed concurrently, minimizing the total time-to-completion for a chain.
*   **Implicit Metadata Inheritance:** To reduce redundancy, metadata (like the `model` or `temperature`) only needs to be defined once in the first prompt step. Subsequent steps automatically inherit these settings unless explicitly overridden. This keeps the Markdown clean and focused on the creative task at hand.
*   **Robust Error Handling:** The parser validates the chain before execution. It checks for missing variables at each step, preventing runtime failures and providing clear, actionable error messages to the user.

#### Example Walkthrough

Let's trace the execution of the sample prompt chain:

1.  **Variable Initialization:** The parser first identifies the `Variables` section and defines a dictionary: `{"topic": "a new line of luxury watches"}`.
2.  **First Prompt Step:**
    *   The parser moves to the first prompt, named `Prompt 1`.
    *   It sees the `[[topic]]` dependency and verifies that `topic` exists in its variables dictionary.
    *   The `[[topic]]` placeholder is replaced with its value, and the resulting prompt is sent to the specified `model` (`openai/gpt-3.5-turbo`).
3.  **Second Prompt Step:**
    *   The parser proceeds to the next prompt, `Draft the body`.
    *   It identifies two dependencies: `[[1]]` and `[[topic]]`.
    *   `[[topic]]` is already known. `[[1]]` refers to the output of the first prompt step. The scheduler (`find_runnable_steps`) would have waited for the first prompt to complete before starting this one.
    *   Once the first prompt's output is received, it's stored as variable `1`. Both placeholders are replaced, and the second prompt is executed.

This step-by-step, dependency-aware process allows for the creation of intricate and powerful workflows from a simple, readable Markdown file.

-   **Implementation:** The logic for parsing the Markdown format and constructing the dependency graph is located in [`promptchain_parser.py`](./promptchain_parser.py). The `find_runnable_steps` function within this file is the core of the DAG scheduler, identifying which prompt steps can be executed in parallel. The execution of the prompt chain is handled by [`promptchain.py`](./promptchain.py).

    ```python
    # From promptchain_parser.py
    def find_runnable_steps(self, variables, promptchain):
        # find all promptchain steps that have their prompt_var_dependancies in the variables
        runnable_steps = []
        for promptstep in promptchain:
            if self.promptstep_var_check(variables, promptstep):
                runnable_steps.append(promptstep)
        return runnable_steps
    ```

### 3. Multi-Model LLM Integration for A/B Testing

Savant is designed to be model-agnostic, using API aggregators like OpenRouter to rapidly A/B test models from OpenAI, Anthropic, and others. This allows for continuous optimization of performance, cost, and output quality.

-   **Implementation:** The integration with OpenRouter and the logic for handling multiple LLM providers is encapsulated in [`openrouter_engine.py`](./openrouter_engine.py).

### 4. BERT-based Email Open Rate Prediction

To further enhance marketing workflows, Savant includes a BERT-based classification model that probabilistically predicts email open rates. This model demonstrated improved Mean Absolute Error and R-squared metrics over baseline regression models.

-   **Developed a BERT-based classification model using Python, TensorFlow, and Hugging Face to probabilistically predict email open rates, which demonstrated improved Mean Absolute Error and R-squared metrics over baseline regression models.**
-   **Engineered a pragmatic, CPU-based multiprocessing solution for deployment, correctly prioritizing stability and ease of deployment over marginal GPU speedups.**
-   **Implementation:** The inference code for the BERT model, including the pragmatic `find_most_recent_ai_model` function for robust model loading, can be found in [`bert_5class_openrate_inference.py`](./bert_5class_openrate_inference.py).

    ```python
    # From bert_5class_openrate_inference.py
    def find_most_recent_ai_model(ai_model_folder_start_name):
        """
        Finds the most recent model folder. Searches up 2 layers. First look in the current dir and then look in all local folders in current dir.
        param: ai_model_folder_start_name: string of start name of the folder that contains the model
        return: the relative path to the most recent model folder.
        """
        # ... implementation ...
    ```

## Getting Started

1.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
2.  **Set up Environment Variables:**
    Create a `.env` file in the root of the project. This file stores sensitive credentials and configuration settings. Below is a more complete example:
    ```
    # Slack API Tokens
    SLACK_TOKEN=xoxb-YOUR_SLACK_BOT_TOKEN
    WEBSOCKET_TOKEN=xapp-YOUR_SLACK_APP_LEVEL_TOKEN

    # LLM Provider API Keys
    OPENROUTER_API_KEY=sk-or-v1-YOUR_OPENROUTER_KEY
    # OPENAI_API_KEY=sk-YOUR_OPENAI_KEY # (Optional, if using OpenAI directly)

    # Other Configurations
    # Add any other necessary environment variables here
    ```
3.  **Run the Server:**
    For detailed instructions on running the server, see [`cmds.md`](./cmds.md).
    ```bash
    python async_server.py
    ```
4.  **Create and Submit a Prompt Chain:**
    Create a file named `my_prompt_chain.md` with your desired workflow.

    **A Note on the Slack UI:** The current method for submitting prompt chains is through a basic UI in the Slack channel where the bot resides. This UI was developed early in the project as a pragmatic way to distribute useful functionality to coworkers. While effective, it has its limitations and was built with limited UI development experience.

    Here is an example `promptchain.md`:
    ```markdown
    ## Variables
    - topic: a new line of luxury watches

    ### Prompt 1
    Write a short, punchy headline for [[topic]].

    ## Metadata
    - model: openai/gpt-3.5-turbo

    ### Draft the body
    [[1]]

    Write a 100-word description of [[topic]].
    ```
    Submit this file through the UI in your Slack channel to trigger the job.

## Prompt Chain Samples

This repository includes a variety of prompt chain samples in the [`promptchain_samples`](./promptchain_samples) directory. These samples demonstrate the power and flexibility of the prompt chaining engine and provide a starting point for creating your own creative workflows.
