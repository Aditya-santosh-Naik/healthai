import {
  AlertTriangle,
  Check,
  ClipboardCopy,
  Info,
  Pill,
  ShieldAlert,
  Utensils,
} from "lucide-react";
import { useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BAND_LABEL, type Band, type Turn } from "@/api/consultation";

/** Ordinal bands only. There is deliberately no number anywhere in here. */
function BandBadge({ band }: { band: Band }) {
  const tone =
    band === "most_consistent"
      ? "bg-primary text-primary-foreground"
      : band === "possible"
        ? "bg-amber-100 text-amber-900"
        : "bg-secondary text-secondary-foreground";
  return <Badge className={tone}>{BAND_LABEL[band]}</Badge>;
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base font-semibold">
          {icon}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm leading-relaxed">{children}</CardContent>
    </Card>
  );
}

function List({ items }: { items: string[] }) {
  return (
    <ul className="space-y-1.5">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2">
          <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-muted-foreground" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        });
      }}
    >
      {copied ? (
        <>
          <Check className="h-3.5 w-3.5" /> Copied
        </>
      ) : (
        <>
          <ClipboardCopy className="h-3.5 w-3.5" /> Copy
        </>
      )}
    </Button>
  );
}

/**
 * Renders a finished consultation.
 *
 * Section order is fixed by spec section 14 and should not be rearranged:
 * urgency -> assessment -> why considered -> what's less likely ->
 * medication safety -> medication guidance -> diet -> lifestyle ->
 * warning signs -> what to tell your doctor -> sources -> disclaimer.
 */
export function ResultView({ turn }: { turn: Turn }) {
  const {
    escalation,
    refusal,
    candidates,
    ruled_out,
    medication_safety,
    medication_guidance,
    diet,
  } = turn;

  // --- refusal: out of scope, nothing else is shown ------------------------
  if (refusal) {
    return (
      <div className="space-y-4">
        <Alert variant="warning">
          <Info className="h-4 w-4" />
          <AlertTitle>This is outside what HealthAI can help with</AlertTitle>
          <AlertDescription className="mt-2 space-y-2">
            <p>{refusal.message}</p>
            <p className="font-medium">{refusal.referral}</p>
          </AlertDescription>
        </Alert>
        {refusal.resources.length > 0 && (
          <Section title="Where to get help now">
            <List items={refusal.resources} />
          </Section>
        )}
      </div>
    );
  }

  // --- escalation: the pipeline halted, so there is no assessment ----------
  if (escalation) {
    return (
      <div className="space-y-4">
        <Alert variant="destructive">
          <ShieldAlert className="h-4 w-4" />
          <AlertTitle className="text-base">
            {escalation.urgency === "emergency"
              ? "Emergency - seek care immediately"
              : "Urgent - seek care today"}
          </AlertTitle>
          <AlertDescription className="mt-2 space-y-2">
            <p>{escalation.reason}</p>
            <p className="font-semibold">{escalation.action}</p>
          </AlertDescription>
        </Alert>

        <Section title="What triggered this">
          <List items={escalation.triggered_by} />
          <p className="text-xs text-muted-foreground">
            HealthAI stopped here on purpose. No condition assessment, medication
            advice, or diet guidance is produced once a warning sign is found.
          </p>
          {escalation.source_url && (
            <a
              href={escalation.source_url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-primary underline underline-offset-2"
            >
              {escalation.source_url}
            </a>
          )}
        </Section>
      </div>
    );
  }

  const band = turn.band ?? "insufficient_information";
  const lessLikely = candidates.slice(1);

  return (
    <div className="space-y-4">
      {/* 1. Urgency / outcome banner */}
      {band === "insufficient_information" ? (
        <Alert variant="warning">
          <Info className="h-4 w-4" />
          <AlertTitle>Not enough information for a confident assessment</AlertTitle>
          <AlertDescription className="mt-1">
            {turn.sufficiency_reason ||
              "Several conditions remain equally consistent with what you have described."}
          </AlertDescription>
        </Alert>
      ) : (
        <Alert variant="info">
          <Info className="h-4 w-4" />
          <AlertTitle>
            {candidates.length > 0
              ? `${BAND_LABEL[band]} ${candidates[0].display_name}`
              : "Assessment"}
          </AlertTitle>
          <AlertDescription className="mt-1">
            This is an evidence summary, not a diagnosis. HealthAI does not give
            probabilities.
          </AlertDescription>
        </Alert>
      )}

      {/* 2. Assessment narrative */}
      {turn.narrative && (
        <Section title="Assessment">
          {turn.narrative.split("\n\n").map((para, i) => (
            <p key={i}>{para}</p>
          ))}
          {turn.used_fallback && (
            <p className="text-xs text-muted-foreground">
              Written from templates because the local language model was
              unavailable. The assessment itself is unaffected -- it is produced by
              the rule engine, not the model.
            </p>
          )}
        </Section>
      )}

      {/* 3. Why this was considered */}
      {candidates.length > 0 && (
        <Section title="Why this was considered">
          <div className="space-y-4">
            {candidates.map((c) => (
              <div key={c.code} className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{c.display_name}</span>
                  <BandBadge band={c.band} />
                </div>
                {c.evidence.supporting.length > 0 && (
                  <p>
                    <span className="text-muted-foreground">Supported by: </span>
                    {c.evidence.supporting.join(", ")}
                  </p>
                )}
                {c.evidence.contradictory.length > 0 && (
                  <p>
                    <span className="text-muted-foreground">Argues against: </span>
                    {c.evidence.contradictory.join(", ")}
                  </p>
                )}
                {c.evidence.missing.length > 0 && (
                  <p>
                    <span className="text-muted-foreground">
                      Expected but not reported:{" "}
                    </span>
                    {c.evidence.missing.join(", ")}
                  </p>
                )}
                {c.context_factors.length > 0 && (
                  <p>
                    <span className="text-muted-foreground">From your profile: </span>
                    {c.context_factors.join(", ")}
                  </p>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* 4. What's less likely.
          Only claim something is "less likely" when its band is genuinely
          weaker than the leader's. When everything sits at the same band,
          nothing has been ranked and saying otherwise would be misleading. */}
      {lessLikely.length > 0 && (
        <Section
          title={
            candidates[0].band === "most_consistent"
              ? "What looks less likely"
              : "Also considered, none clearly ahead"
          }
        >
          <List
            items={lessLikely.map((c) =>
              c.evidence.contradictory.length > 0
                ? `${c.display_name} - argued against by ${c.evidence.contradictory.join(", ")}`
                : c.evidence.missing.length > 0
                  ? `${c.display_name} - would usually also involve ${c.evidence.missing.join(", ")}`
                  : `${c.display_name} - still consistent with what you have described`,
            )}
          />
          {candidates[0].band !== "most_consistent" && (
            <p className="text-xs text-muted-foreground">
              These remain equally consistent on the evidence available.
              Separating them needs tests HealthAI cannot run.
            </p>
          )}
        </Section>
      )}

      {/* 4b. Considered and set aside.
          Answers "but couldn't it be a cold?" from the page itself, instead
          of leaving the user to wonder whether it was looked at. */}
      {ruled_out && ruled_out.length > 0 && (
        <Section title="Also considered, and set aside">
          <p className="text-xs text-muted-foreground">
            These were checked against your symptoms and did not fit.
          </p>
          <ul className="space-y-2">
            {ruled_out.map((c) => {
              const against = [
                ...c.evidence.contradictory.map((x) => `you reported ${x.toLowerCase()}`),
                ...c.evidence.missing.map(
                  (x) => `it would usually involve ${x.toLowerCase()}`,
                ),
              ];
              return (
                <li key={c.code} className="flex gap-2">
                  <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-muted-foreground" />
                  <span>
                    <span className="font-medium">{c.display_name}</span>
                    {against.length > 0 && (
                      <span className="text-muted-foreground"> — {against.join("; ")}</span>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </Section>
      )}

      {/* 5. Medication safety.
          Spec section 10 defines three tiers, and no_known_conflict is one of
          them. Showing nothing when the check found nothing hides the fact
          that the check ran at all. */}
      {medication_safety &&
        medication_safety.findings.length === 0 &&
        medication_safety.checked_medicines.length > 0 && (
          <Section
            title="Medication safety"
            icon={<ShieldAlert className="h-4 w-4 text-primary" />}
          >
            <div className="rounded-lg border border-primary/30 bg-accent/40 p-3">
              <div className="mb-1 flex items-center gap-2">
                <Badge variant="secondary" className="uppercase">
                  No known conflict
                </Badge>
              </div>
              <p>
                Your current medicines (
                {medication_safety.checked_medicines.join(", ")}) were checked
                against each other, your allergies, your conditions, and the
                symptoms you reported. Nothing known came up.
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                This covers the medicines and interactions in this project's
                database only. Always tell your doctor or pharmacist everything
                you take, including anything bought without a prescription.
              </p>
            </div>
            {medication_safety.unrecognised.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Not recognised, so not checked:{" "}
                {medication_safety.unrecognised.join(", ")}. Ask your pharmacist
                about these.
              </p>
            )}
          </Section>
        )}

      {medication_safety && medication_safety.findings.length > 0 && (
        <Section
          title="Medication safety"
          icon={<ShieldAlert className="h-4 w-4 text-amber-600" />}
        >
          <p className="text-xs text-muted-foreground">
            Checked against your own medicines
            {medication_safety.checked_medicines.length > 0 &&
              `: ${medication_safety.checked_medicines.join(", ")}`}
          </p>
          <div className="space-y-3">
            {medication_safety.findings.map((f, i) => (
              <div
                key={i}
                className={`rounded-lg border p-3 ${
                  f.severity === "avoid"
                    ? "border-destructive/40 bg-destructive/5"
                    : "border-amber-300 bg-amber-50"
                }`}
              >
                <div className="mb-1 flex items-center gap-2">
                  <Badge
                    variant={f.severity === "avoid" ? "destructive" : "secondary"}
                    className="uppercase"
                  >
                    {f.severity}
                  </Badge>
                  <span className="text-sm font-medium">{f.subject_drug}</span>
                </div>
                <p>{f.reason}</p>
                {f.source_url && (
                  <a
                    href={f.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-primary underline underline-offset-2"
                  >
                    Source
                  </a>
                )}
              </div>
            ))}
          </div>
          {medication_safety.unrecognised.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Not recognised, so not checked:{" "}
              {medication_safety.unrecognised.join(", ")}. Ask your pharmacist about
              these.
            </p>
          )}
        </Section>
      )}

      {/* 6. Medication guidance: three tiers, never a prescription */}
      {medication_guidance &&
        (medication_guidance.treatment.length > 0 ||
          medication_guidance.general_info.length > 0) && (
          <Section
            title="Medication guidance"
            icon={<Pill className="h-4 w-4 text-primary" />}
          >
            {medication_guidance.treatment.length > 0 && (
              <div className="space-y-2">
                <p className="font-medium">What this usually needs</p>
                {medication_guidance.treatment.map((t, i) => (
                  <div key={i} className="rounded-lg border bg-muted/40 p-3">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className="font-medium">{t.condition_display}</span>
                      {t.needs_prescription ? (
                        <Badge variant="destructive">Needs a doctor's prescription</Badge>
                      ) : t.self_limiting ? (
                        <Badge variant="secondary">Usually settles on its own</Badge>
                      ) : null}
                    </div>
                    <p>{t.summary}</p>
                  </div>
                ))}
              </div>
            )}

            {medication_guidance.general_info.length > 0 && (
              <div className="space-y-2 pt-2">
                <p className="font-medium">General information</p>
                <p className="text-xs text-muted-foreground">
                  General information only, not a recommendation for you, and no doses
                  are given. Confirm anything here with a doctor or pharmacist.
                </p>
                {medication_guidance.general_info.map((g, i) => (
                  <div key={i} className="rounded-lg border p-3">
                    <p className="font-medium">{g.display}</p>
                    <p className="text-muted-foreground">Used for {g.used_for}.</p>
                    <p className="mt-1">{g.caveat}</p>
                  </div>
                ))}
              </div>
            )}
          </Section>
        )}

      {/* 7. Diet */}
      {diet && (diet.prefer.length > 0 || diet.avoid.length > 0) && (
        <Section title="Diet" icon={<Utensils className="h-4 w-4 text-primary" />}>
          <p className="text-xs text-muted-foreground">
            Filtered for your diet type, allergies and existing conditions.
          </p>
          {diet.prefer.length > 0 && (
            <div>
              <p className="mb-1 font-medium">Helpful</p>
              <List items={diet.prefer} />
            </div>
          )}
          {diet.avoid.length > 0 && (
            <div>
              <p className="mb-1 font-medium">Better avoided</p>
              <List items={diet.avoid} />
            </div>
          )}
          {diet.hydration.length > 0 && (
            <div>
              <p className="mb-1 font-medium">Fluids</p>
              <List items={diet.hydration} />
            </div>
          )}
        </Section>
      )}

      {/* 8. Lifestyle */}
      {diet && diet.lifestyle.length > 0 && (
        <Section title="Lifestyle">
          <List items={diet.lifestyle} />
          {diet.monitor.length > 0 && (
            <div className="pt-2">
              <p className="mb-1 font-medium">Keep an eye on</p>
              <List items={diet.monitor} />
            </div>
          )}
        </Section>
      )}

      {/* 9. Warning signs */}
      {diet && diet.warning_signs.length > 0 && (
        <Section
          title="Warning signs - seek care if these appear"
          icon={<AlertTriangle className="h-4 w-4 text-destructive" />}
        >
          <List items={diet.warning_signs} />
        </Section>
      )}

      {/* 10. What to tell your doctor */}
      {turn.doctor_summary && (
        <Card className="border-primary/30 bg-accent/40">
          <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
            <CardTitle className="text-base font-semibold">
              What to tell your doctor
            </CardTitle>
            <CopyButton text={turn.doctor_summary} />
          </CardHeader>
          <CardContent>
            <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
              {turn.doctor_summary}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* 11. Sources */}
      {turn.sources.length > 0 && (
        <Section title="Sources">
          <ul className="space-y-1.5">
            {turn.sources.map((s, i) => (
              <li key={i}>
                <span className="text-muted-foreground">{s.name} </span>
                {s.url && (
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    className="break-all text-primary underline underline-offset-2"
                  >
                    {s.url}
                  </a>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* 12. Disclaimer */}
      <p className="px-1 text-xs leading-relaxed text-muted-foreground">
        {turn.disclaimer}
      </p>
    </div>
  );
}
