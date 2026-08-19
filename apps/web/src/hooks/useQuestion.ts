import { useState } from "react";
import type { FormEvent } from "react";
import { askQuestion } from "../api";
import type { QuestionResponse } from "../api";

export function useQuestion(snapshotId: string | undefined) {
  const [question, setQuestion] = useState("Who owns payments-api?");
  const [answer, setAnswer] = useState<QuestionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (snapshotId === undefined || question.trim().length < 3) return;
    setPending(true);
    setError(null);
    try {
      setAnswer(await askQuestion(snapshotId, question));
    } catch (reason) {
      setAnswer(null);
      setError(reason instanceof Error ? reason.message : "Question failed");
    } finally {
      setPending(false);
    }
  }

  return { answer, error, pending, question, setQuestion, submit };
}
