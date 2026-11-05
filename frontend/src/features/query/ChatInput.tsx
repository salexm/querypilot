import { type FormEvent, type KeyboardEvent, useState } from "react";

interface ChatInputProps {
  isPending: boolean;
  onSend: (question: string) => void;
}

const MAX_QUESTION_LENGTH = 500;

export function ChatInput({ isPending, onSend }: ChatInputProps) {
  const [text, setText] = useState("");
  const canSend = text.trim().length > 0 && !isPending;

  function send() {
    if (canSend) {
      onSend(text.trim());
      setText("");
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    send();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send();
    }
  }

  return (
    <form className="chat-input" onSubmit={handleSubmit}>
      <label htmlFor="question" className="visually-hidden">
        Your question
      </label>
      <textarea
        id="question"
        rows={1}
        value={text}
        maxLength={MAX_QUESTION_LENGTH}
        placeholder="Ask about orders, products, sellers, or reviews…"
        onChange={(event) => setText(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      <button type="submit" disabled={!canSend}>
        Send
      </button>
    </form>
  );
}
