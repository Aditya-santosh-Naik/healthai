import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Download, FileText, Loader2, Trash2 } from "lucide-react";
import { Layout } from "@/components/Layout";
import { ResultView } from "@/components/ResultView";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api, ApiError, getToken } from "@/api/client";
import type { HistoryDetail, HistoryItem } from "@/api/consultation";

/** DD/MM/YYYY, per spec section 15. */
function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(
    2,
    "0",
  )}/${d.getFullYear()} ${String(d.getHours()).padStart(2, "0")}:${String(
    d.getMinutes(),
  ).padStart(2, "0")}`;
}

function statusBadge(status: string) {
  if (status === "escalated") return <Badge variant="destructive">Urgent</Badge>;
  if (status === "refused") return <Badge variant="secondary">Out of scope</Badge>;
  if (status === "in_progress") return <Badge variant="outline">Unfinished</Badge>;
  return <Badge variant="secondary">Complete</Badge>;
}

export function HistoryList() {
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setItems(await api.get<HistoryItem[]>("/api/history"));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load history.");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function remove(id: number) {
    await api.del(`/api/history/${id}`);
    void load();
  }

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">History</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Past consultations are kept as a record. They are never treated as
          confirmed medical facts about you.
        </p>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {items === null && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading...
        </div>
      )}

      {items?.length === 0 && (
        <Card>
          <CardContent className="py-10 text-center">
            <FileText className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No consultations yet.{" "}
              <Link to="/consultation" className="text-primary underline">
                Start one
              </Link>
              .
            </p>
          </CardContent>
        </Card>
      )}

      <div className="space-y-3">
        {items?.map((item) => (
          <Card key={item.id}>
            <CardContent className="flex items-center gap-4 py-4">
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  {statusBadge(item.status)}
                  <span className="text-xs text-muted-foreground">
                    {formatDate(item.started_at)}
                  </span>
                </div>
                <p className="truncate text-sm font-medium">{item.summary}</p>
              </div>
              <Button variant="outline" size="sm" asChild>
                <Link to={`/history/${item.id}`}>View</Link>
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => void remove(item.id)}
                aria-label="Delete consultation"
              >
                <Trash2 className="h-4 w-4 text-muted-foreground" />
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </Layout>
  );
}

export function HistoryDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [detail, setDetail] = useState<HistoryDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<HistoryDetail>(`/api/history/${id}`)
      .then(setDetail)
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "Could not load consultation."),
      );
  }, [id]);

  function downloadPdf() {
    void fetch(`/api/reports/${id}.pdf`, {
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
    })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `healthai_consultation_${id}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      });
  }

  return (
    <Layout>
      <div className="mb-6 flex items-center gap-3">
        <Button variant="ghost" size="sm" asChild>
          <Link to="/history">
            <ArrowLeft className="h-4 w-4" /> Back
          </Link>
        </Button>
        {detail && (
          <span className="text-sm text-muted-foreground">
            {formatDate(detail.started_at ?? new Date().toISOString())}
          </span>
        )}
        <Button variant="outline" size="sm" className="ml-auto" onClick={downloadPdf}>
          <Download className="h-4 w-4" /> PDF
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {detail === null && !error && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading...
        </div>
      )}

      {detail && (
        <div className="space-y-4">
          {detail.messages.length > 0 && (
            <Card>
              <CardContent className="space-y-2 pt-6">
                <p className="text-sm font-medium">Transcript</p>
                {detail.messages.map((m, i) => (
                  <div
                    key={i}
                    className={m.role === "user" ? "flex justify-end" : "flex justify-start"}
                  >
                    <div
                      className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
                        m.role === "user"
                          ? "rounded-br-sm bg-primary text-primary-foreground"
                          : "rounded-bl-sm border"
                      }`}
                    >
                      {m.content}
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
          <ResultView turn={detail} />
        </div>
      )}
    </Layout>
  );
}
