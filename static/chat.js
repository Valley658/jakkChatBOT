document.addEventListener('DOMContentLoaded', function() {
    const chatForm = document.getElementById('chat-form');
    const messageInput = document.getElementById('message');
    const chatBox = document.getElementById('chat-box');

    chatForm.addEventListener('submit', function(event) {
        event.preventDefault();
        sendMessage();
    });

    messageInput.addEventListener('keydown', function(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    });

    function sendMessage() {
        const message = messageInput.value.trim();
        if (message === '') return;

        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/chat', true);
        xhr.setRequestHeader('Content-Type', 'application/json;charset=UTF-8');
        xhr.onload = function() {
            if (xhr.status === 200) {
                const response = JSON.parse(xhr.responseText);
                appendMessage('You', response.user_input);
                appendMessage('Bot', response.bot_response);
                const audio = new Audio(response.audio_url);
                audio.play();
            }
        };
        xhr.send(JSON.stringify({ message: message }));

        messageInput.value = '';
    }

    function appendMessage(sender, message) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('message');
        messageElement.innerHTML = `<strong>${sender}:</strong> ${message}`;
        chatBox.appendChild(messageElement);
        chatBox.scrollTop = chatBox.scrollHeight;
    }
});
