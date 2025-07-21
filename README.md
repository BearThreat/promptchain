# Savant: An AI-Powered Slack Workflow Automation Platform

Savant is a sophisticated, AI-driven Slack bot designed to enhance marketing and copywriting workflows. It integrates with multiple large language models (LLMs) to automate complex creative tasks, streamline content generation, and dramatically boost productivity, all within the familiar Slack interface.

## Core Features & Technical Deep Dive

This repository showcases the core logic of the Savant platform, demonstrating advanced concepts in AI engineering, asynchronous programming, and system architecture.

### 1. AI-Powered Slack Automation & Creative Partnership

Savant transforms a simple classification analysis tool into a powerful creative partner for marketing teams. It breaks down complex writing tasks into sequential, manageable stages, guiding copywriters through the creative process.

-   **Implementation:** The core of the Slack integration can be found in [`async_server.py`](./async_server.py), which handles the main application loop, and [`slack_custom_actions.py`](./slack_custom_actions.py), which manages custom interactions and commands within Slack.

### 2. Custom DAG-based Prompt Chaining Engine

At the heart of Savant is a custom-built Directed Acyclic Graph (DAG) execution engine. This system parses a domain-specific Markdown format to define complex prompt dependencies, allowing the output of one LLM call to be used as a variable input for subsequent calls.

-   **Engineered a custom Directed Acyclic Graph (DAG) execution engine from the ground up, parsing a domain-specific Markdown format to define complex prompt dependencies. The engine's scheduler (`find_runnable_steps` in `promptchain_parser.py`) identifies parallelizable tasks, enabling non-blocking, concurrent API calls that significantly minimize generation latency.**
-   **Implementation:** The logic for parsing the Markdown format and constructing the dependency graph is located in [`promptchain_parser.py`](./promptchain_parser.py). The `find_runnable_steps` function within this file is the core of the DAG scheduler, identifying which prompt steps can be executed in parallel. The execution of the prompt chain is handled by [`promptchain.py`](./promptchain.py).

### 3. Multi-Model LLM Integration for A/B Testing

Savant is designed to be model-agnostic, using API aggregators like OpenRouter to rapidly A/B test models from OpenAI, Anthropic, and others. This allows for continuous optimization of performance, cost, and output quality.

-   **Implementation:** The integration with OpenRouter and the logic for handling multiple LLM providers is encapsulated in [`openrouter_engine.py`](./openrouter_engine.py).

### 4. BERT-based Email Open Rate Prediction

To further enhance marketing workflows, Savant includes a BERT-based classification model that probabilistically predicts email open rates. This model demonstrated improved Mean Absolute Error and R-squared metrics over baseline regression models.

-   **Developed a BERT-based classification model using Python, TensorFlow, and Hugging Face to probabilistically predict email open rates, which demonstrated improved Mean Absolute Error and R-squared metrics over baseline regression models.**
-   **Engineered a pragmatic, CPU-based multiprocessing solution for deployment, correctly prioritizing stability and ease of deployment over marginal GPU speedups.**
-   **Implementation:** The inference code for the BERT model, including the pragmatic `find_most_recent_ai_model` function for robust model loading, can be found in [`bert_5class_openrate_inference.py`](./bert_5class_openrate_inference.py).

## How to Run

1.  Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```
2.  Set up your environment variables in a `.env` file.
3.  Run the main application server:
    ```bash
    python async_server.py
