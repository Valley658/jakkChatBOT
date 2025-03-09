# jakkChatBOT

## Overview
jakkChatBOT is a chatbot application built using Flask, SQLAlchemy, and various machine learning models including GPT-2 and T5. It supports multiple languages and includes features like speech-to-text and text-to-speech.

## Features
- User authentication and registration
- Chat with memory stored in a database
- Automatic language detection and translation
- Speech-to-text and text-to-speech functionality
- System status monitoring (CPU, memory, GPU usage)
- Admin dashboard for managing users and system status

## Setup

### Prerequisites
- Python 3.10 or higher
- Flask
- SQLAlchemy
- TensorFlow
- PyTorch
- OpenAI API key

### Installation
1. Install the required packages:
    ```sh
    pip install -r requirements.txt
    ```

2. Set up the database:
    ```sh
    flask db upgrade
    ```

3. Run the application:
    ```sh
    flask run
    ```

## Usage
- Access the application at `http://localhost:5000`
- Register a new user or log in with an existing account
- Use the chat interface to interact with the chatbot
- Admin users can access the dashboard at `http://localhost:5000/dashboard`

## Additional Features
- Text-to-speech: Convert text to speech and play it in the browser
- System status: Monitor CPU, memory, and GPU usage

## License
This project is licensed under the MIT License.