import { useEffect, useRef, useState } from "react";
import { Check, FileUp, Loader2, Upload, X } from "lucide-react";
import { Layout } from "@/components/Layout";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { api, ApiError, getToken } from "@/api/client";

interface Fact {
  id: number;
  fact_type: string;
  fact_value: string;
  confidence: number | null;
  page_ref: number | null;
  review_status: string;
}

interface Doc {
  id: number;
  filename: string;
  uploaded_at: string;
  extraction_status: string;
  page_count: number | null;
  message?: string;
  facts: Fact[];
}

const TYPE_LABEL: Record<string, string> = {
  condition: "Condition",
  allergy: "Allergy",
  medication: "Medicine",
};

export default function Documents() {
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [active, setActive] = useState<Doc | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    try {
      setDocs(await api.get<Doc[]>("/api/documents"));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load documents.");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/documents", {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken() ?? ""}` },
        body: form,
      });
      const payload = (await response.json()) as Doc & { detail?: string };
      if (!response.ok) throw new ApiError(response.status, payload.detail ?? "Upload failed");

      setActive(payload);
      // Pre-tick only the confident ones; the user still confirms every item.
      setSelected(new Set(payload.facts.filter((f) => (f.confidence ?? 0) >= 0.8).map((f) => f.id)));
      if (payload.message) setNotice(payload.message);
      void load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed.");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function confirm() {
    if (!active) return;
    setBusy(true);
    try {
      const pending = active.facts.filter((f) => f.review_status === "pending");
      const updated = await api.post<Doc>(`/api/documents/${active.id}/confirm`, {
        fact_ids: [...selected],
        rejected_ids: pending.filter((f) => !selected.has(f.id)).map((f) => f.id),
      });
      setActive(updated);
      setNotice(
        `Added ${selected.size} item${selected.size === 1 ? "" : "s"} to your profile.`,
      );
      void load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  const pending = active?.facts.filter((f) => f.review_status === "pending") ?? [];

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Upload a prescription or discharge summary as a PDF. Nothing is added to
          your profile until you confirm it.
        </p>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {notice && (
        <Alert variant="info" className="mb-4">
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      )}

      <Card className="mb-4">
        <CardContent className="pt-6">
          <input
            ref={fileRef}
            type="file"
            accept="application/pdf"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void upload(file);
            }}
          />
          <div className="flex flex-col items-center gap-3 rounded-lg border-2 border-dashed py-10">
            <FileUp className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              Text-based PDFs only. Scanned images cannot be read.
            </p>
            <Button onClick={() => fileRef.current?.click()} disabled={busy}>
              {busy ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Reading...
                </>
              ) : (
                <>
                  <Upload className="h-4 w-4" /> Choose a PDF
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* review step: this is the only path into the profile */}
      {active && pending.length > 0 && (
        <Card className="mb-4 border-primary/30">
          <CardHeader>
            <CardTitle className="text-base">
              Confirm what was found in {active.filename}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              These were read automatically and may be wrong. Tick only what is
              correct. Unticked items are discarded.
            </p>
            {pending.map((fact) => (
              <label
                key={fact.id}
                className="flex cursor-pointer items-center gap-3 rounded-lg border p-3 hover:bg-accent/40"
              >
                <Checkbox
                  checked={selected.has(fact.id)}
                  onCheckedChange={(checked) => {
                    const next = new Set(selected);
                    if (checked) next.add(fact.id);
                    else next.delete(fact.id);
                    setSelected(next);
                  }}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="secondary">
                      {TYPE_LABEL[fact.fact_type] ?? fact.fact_type}
                    </Badge>
                    <span className="text-sm font-medium">{fact.fact_value}</span>
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {fact.confidence !== null &&
                      (fact.confidence >= 0.8 ? "Clear match" : "Uncertain match")}
                    {fact.page_ref !== null && ` - page ${fact.page_ref}`}
                  </p>
                </div>
              </label>
            ))}
            <Button onClick={() => void confirm()} disabled={busy}>
              <Check className="h-4 w-4" /> Add {selected.size} to my profile
            </Button>
          </CardContent>
        </Card>
      )}

      {active && pending.length === 0 && active.facts.length > 0 && (
        <Alert variant="info" className="mb-4">
          <AlertTitle>Review complete</AlertTitle>
          <AlertDescription>
            {active.facts.filter((f) => f.review_status === "confirmed").length} item(s)
            added to your profile,{" "}
            {active.facts.filter((f) => f.review_status === "rejected").length} discarded.
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Uploaded documents</CardTitle>
        </CardHeader>
        <CardContent>
          {docs?.length === 0 && (
            <p className="text-sm text-muted-foreground">Nothing uploaded yet.</p>
          )}
          <div className="space-y-2">
            {docs?.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center gap-3 rounded-lg border p-3 text-sm"
              >
                <span className="min-w-0 flex-1 truncate font-medium">{doc.filename}</span>
                {doc.extraction_status === "complete" ? (
                  <Badge variant="secondary">
                    {doc.facts.filter((f) => f.review_status === "confirmed").length} added
                  </Badge>
                ) : doc.extraction_status === "no_text_layer" ? (
                  <Badge variant="outline">
                    <X className="mr-1 h-3 w-3" /> Scanned, unreadable
                  </Badge>
                ) : (
                  <Badge variant="outline">{doc.extraction_status}</Badge>
                )}
                <Button variant="ghost" size="sm" onClick={() => {
                  setActive(doc);
                  setSelected(new Set());
                }}>
                  Review
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </Layout>
  );
}
