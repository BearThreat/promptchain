# Savant Command-Line Operations

This document provides a reference for essential command-line operations for running, debugging, and managing the Savant server.

## Server Management

### Running the Main Server

This command starts the main asynchronous server, which listens for Slack events and handles all incoming requests.

```bash
python async_server.py
```

### Running with Debugging

To run the server in a more verbose mode for debugging, you can use Python's interactive mode or other debugging tools. For instance, to inspect the application state at a certain point, you might add `import pdb; pdb.set_trace()` to the code.

## Git Management

These are standard Git commands useful for managing your local repository and synchronizing with the remote.

### Checking Current Status

View the state of your local working directory and staging area.

```bash
git status
```

### Staging Changes

Stage all modified and new files for the next commit.

```bash
git add .
```

### Committing Changes

Commit your staged changes with a descriptive message.

```bash
git commit -m "Your descriptive commit message"
```

### Pushing to Remote

Push your committed changes to the `main` branch of the remote repository.

```bash
git push origin main
```

### Pulling from Remote

Fetch and merge the latest changes from the remote `main` branch into your local repository.

```bash
git pull origin main
