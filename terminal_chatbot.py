from chatbot import get_response

def main():
    print("Welcome to the terminal chatbot! Type 'exit' to quit.")
    while True:
        user_input = input("You: ")
        if user_input.lower() == 'exit':
            break
        bot_response = get_response(user_input)
        print(f"Bot: {bot_response}")

if __name__ == '__main__':
    main()
