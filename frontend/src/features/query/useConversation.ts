import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { type ApiError, askQuestion, type QueryResponse } from "../../api/client";

interface TurnBase {
  id: number;
  question: string;
}

export type Turn =
  | (TurnBase & { status: "pending" })
  | (TurnBase & { status: "success"; result: QueryResponse })
  | (TurnBase & { status: "error"; error: ApiError });

export function useConversation() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const nextId = useRef(0);
  const ask = useMutation<QueryResponse, ApiError, string>({ mutationFn: askQuestion });

  function settle(id: number, turn: Turn) {
    setTurns((current) => current.map((item) => (item.id === id ? turn : item)));
  }

  function send(question: string) {
    const id = nextId.current++;
    setTurns((current) => [...current, { id, question, status: "pending" }]);
    ask.mutate(question, {
      onSuccess: (result) => settle(id, { id, question, status: "success", result }),
      onError: (error) => settle(id, { id, question, status: "error", error }),
    });
  }

  return { turns, send, isPending: ask.isPending };
}
