import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Download, Loader2, RotateCcw, Send, ThumbsDown, ThumbsUp } from "lucide-react";
import { Layout } from "@/components/Layout";
import { ResultView } from "@/components/ResultView";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, ApiError, getToken } from "@/api/client";
import type { Turn } from "@/api/consultation";

interface ChatLine {
  role: "user" | "assistant";
  text: string;
}

const EXAMPLES = [
  "I have fever and cough",
  "Loose motions since yesterday and my stomach hurts",
  "Burning in my chest after eating, worse when I lie down",
];

export default function Consultation() {
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [turn, setTurn] = useState<Turn | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedbackSent, setFeedbackSent] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  const finished =
    turn !== null &&
    (turn.outcome === "complete" ||
      turn.outcome === "escalated" ||
      turn.outcome === "refused");

  useEffect(() => {
    // Scrolling to the bottom is right for a one-line follow-up question, but
    // the final result is taller than the viewport -- doing it there lands the
    // user on the closing disclaimer with the urgency banner and the
    // assessment scrolled off the top. Anchor to the START of the result
    // instead, and let them scroll down through it.
    if (finished) {
      resultRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
      return;
    }
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines, turn, finished]);

  function applyTurn(next: Turn) {
    setTurn(next);
    if (next.question) {
      setLines((prev) => [...prev, { role: "assistant", text: next.question!.text }]);
    }
  }

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setError(null);
    setBusy(true);
    setLines((prev) => [...prev, { role: "user", text }]);
    setInput("");
    try {
      const next = turn
        ? await api.post<Turn>(`/api/consultation/${turn.consultation_id}/message`, {
            text,
          })
        : await api.post<Turn>("/api/consultation/start", { text });
      applyTurn(next);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  async function answer(option: string) {
    if (!turn?.question || busy) return;
    setError(null);
    setBusy(true);
    setLines((prev) => [...prev, { role: "user", text: option }]);
    try {
      const next = await api.post<Turn>(
        `/api/consultation/${turn.consultation_id}/answer`,
        { symptom_code: turn.question.symptom_code, answer: option },
      );
      applyTurn(next);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  async function sendFeedback(helpful: boolean) {
    if (!turn) return;
    try {
      await api.post(`/api/consultation/${turn.consultation_id}/feedback`, { helpful });
      setFeedbackSent(true);
    } catch {
      /* feedback is best-effort; never block the user on it */
    }
  }

  function reset() {
    setLines([]);
    setTurn(null);
    setInput("");
    setError(null);
    setFeedbackSent(false);
  }

  function downloadPdf() {
    if (!turn) return;
    // The endpoint needs the bearer token, so fetch it and hand the browser a blob.
    void fetch(`/api/reports/${turn.consultation_id}.pdf`, {
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
    })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `healthai_consultation_${turn.consultation_id}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      });
  }

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Consultation</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Describe what you are feeling in your own words. HealthAI asks follow-up
          questions rather than guessing.
        </p>
      </div>

      {lines.length === 0 && (
        <Card className="mb-4">
          <CardContent className="space-y-3 pt-6">
            <p className="text-sm text-muted-foreground">Try something like:</p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((e) => (
                <Button
                  key={e}
                  variant="outline"
                  size="sm"
                  onClick={() => void send(e)}
                  disabled={busy}
                  // The shadcn Button is whitespace-nowrap by default, which is
                  // right for "Save" and wrong for a full sentence: on a phone
                  // these example prompts ran off the screen and took the whole
                  // page sideways with them.
                  className="h-auto max-w-full whitespace-normal py-1.5 text-left"
                >
                  {e}
                </Button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* transcript */}
      {lines.length > 0 && (
        <div className="mb-4 space-y-3">
          {lines.map((line, i) => (
            <div
              key={i}
              className={line.role === "user" ? "flex justify-end" : "flex justify-start"}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                  line.role === "user"
                    ? "rounded-br-sm bg-primary text-primary-foreground"
                    : "rounded-bl-sm border bg-background"
                }`}
              >
                {line.text}
              </div>
            </div>
          ))}
        </div>
      )}

      {busy && (
        <div className="mb-4 flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Working through the evidence...
        </div>
      )}

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* follow-up question with tappable options */}
      {turn?.question && !busy && (
        <Card className="mb-4 border-primary/30">
          <CardContent className="space-y-3 pt-6">
            <div className="flex items-center gap-2">
              <Badge variant={turn.question.kind === "safety" ? "destructive" : "secondary"}>
                {turn.question.kind === "safety" ? "Safety check" : "Narrowing it down"}
              </Badge>
              <span className="text-xs text-muted-foreground">
                Question {turn.questions_asked}
              </span>
            </div>
            <p className="font-medium">{turn.question.text}</p>
            <div className="flex flex-wrap gap-2">
              {turn.question.options.map((opt) => (
                <Button key={opt} variant="outline" onClick={() => void answer(opt)}>
                  {opt}
                </Button>
              ))}
            </div>
            {turn.question.rationale && (
              <p className="text-xs text-muted-foreground">{turn.question.rationale}</p>
            )}
          </CardContent>
        </Card>
      )}

      {/* result */}
      {finished && turn && (
        <div ref={resultRef} className="scroll-mt-4 space-y-4">
          <ResultView turn={turn} />

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" onClick={downloadPdf}>
              <Download className="h-4 w-4" /> Download PDF
            </Button>
            <Button variant="outline" onClick={reset}>
              <RotateCcw className="h-4 w-4" /> New consultation
            </Button>
            <Button variant="ghost" asChild>
              <Link to="/history">View history</Link>
            </Button>

            <div className="ml-auto flex items-center gap-2">
              {feedbackSent ? (
                <span className="text-sm text-muted-foreground">
                  Thanks for the feedback.
                </span>
              ) : (
                <>
                  <span className="text-sm text-muted-foreground">Was this helpful?</span>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => void sendFeedback(true)}
                  >
                    <ThumbsUp className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => void sendFeedback(false)}
                  >
                    <ThumbsDown className="h-4 w-4" />
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* input */}
      {!finished && (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void send(input);
          }}
        >
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              turn?.question
                ? "Or type your answer instead..."
                : "Describe your symptoms in your own words..."
            }
            disabled={busy}
          />
          <Button type="submit" disabled={busy || !input.trim()}>
            <Send className="h-4 w-4" />
          </Button>
        </form>
      )}

      <div ref={endRef} />
    </Layout>
  );
}
