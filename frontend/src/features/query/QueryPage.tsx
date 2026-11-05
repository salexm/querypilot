import { useEffect, useRef } from "react";

import { ChatInput } from "./ChatInput";
import { EXAMPLE_QUESTIONS } from "./exampleQuestions";
import { QueryErrorMessage } from "./QueryErrorMessage";
import { QueryResultView } from "./QueryResultView";
import { type Turn, useConversation } from "./useConversation";

function Answer({ turn }: { turn: Turn }) {
  if (turn.status === "pending") {
    return (
      <p className="loading" role="status">
        <span className="spinner" aria-hidden="true" />
        Writing SQL and running the query…
      </p>
    );
  }
  if (turn.status === "error") {
    return <QueryErrorMessage error={turn.error} />;
  }
  return <QueryResultView result={turn.result} />;
}

function Welcome({ onPick }: { onPick: (question: string) => void }) {
  return (
    <section className="welcome" aria-label="Example questions">
      <h1>QueryPilot</h1>
      <p className="muted">Ask a question about 100,000 orders from a Brazilian marketplace.</p>
      <ul className="examples">
        {EXAMPLE_QUESTIONS.map((example) => (
          <li key={example}>
            <button type="button" className="example" onClick={() => onPick(example)}>
              {example}
            </button>
          </li>
        ))}
      </ul>
      <p className="attribution muted">
        Data:{" "}
        <a href="https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce">Olist dataset</a>,{" "}
        <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/">CC BY-NC-SA 4.0</a>
      </p>
    </section>
  );
}

export function QueryPage() {
  const { turns, send, isPending } = useConversation();
  const latestTurn = useRef<HTMLElement>(null);

  useEffect(() => {
    latestTurn.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, [turns.length]);

  return (
    <div className="app">
      <main className="thread" aria-live="polite">
        <div className="thread-content">
          {turns.length === 0 && <Welcome onPick={send} />}
          {turns.map((turn, index) => (
            <article
              key={turn.id}
              className="turn"
              ref={index === turns.length - 1 ? latestTurn : undefined}
            >
              <p className="user-message">{turn.question}</p>
              <Answer turn={turn} />
            </article>
          ))}
        </div>
      </main>
      <footer className="composer">
        <ChatInput isPending={isPending} onSend={send} />
      </footer>
    </div>
  );
}
