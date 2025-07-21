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

At the heart of Savant is a custom-built Directed Acyclic Graph (DAG) execution engine. This system parses a domain-specific Markdown format to define complex prompt dependencies, allowing the output of one LLM call to be used as a variable input for subsequent calls.

-   **Engineered a custom Directed Acyclic Graph (DAG) execution engine from the ground up, parsing a domain-specific Markdown format to define complex prompt dependencies. The engine's scheduler (`find_runnable_steps` in `promptchain_parser.py`) identifies parallelizable tasks, enabling non-blocking, concurrent API calls that significantly minimize generation latency.**
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
    Create a `.env` file in the root of the project and add the following:
    ```
    SLACK_TOKEN=xoxb-...
    WEBSOCKET_TOKEN=xapp-...
    ```
3.  **Run the Server:**
    ```bash
    python async_server.py
    ```
4.  **Create a Prompt Chain:**
    Create a file named `my_prompt_chain.md` with the following content:
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
5.  **Trigger the Job:**
    In Slack, use the `/savant` command to trigger the prompt chain.

## Prompt Chain Samples

This repository includes a variety of prompt chain samples in the [`promptchain_samples`](./promptchain_samples) directory. These samples demonstrate the power and flexibility of the prompt chaining engine and provide a starting point for creating your own creative workflows.
