import { useState } from "react";
import { Plus, X } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Layout } from "@/components/Layout";
import { api } from "@/api/client";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import type { DietType, ProfileOut } from "@/api/types";

export default function Profile() {
  const { profile, refreshProfile } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [conditionDraft, setConditionDraft] = useState("");
  const [allergyDraft, setAllergyDraft] = useState("");
  const [medDraft, setMedDraft] = useState("");

  if (!profile) return null;

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      await refreshProfile();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  return (
    <Layout>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Your profile</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Everything here is entered or confirmed by you. Nothing the AI infers is ever
          saved here without your confirmation.
        </p>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-lg">Details</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          <Detail label="Name" value={profile.name} />
          <Detail label="Age" value={String(profile.age)} />
          <Detail label="Sex" value={profile.sex} capitalize />
          <Detail
            label="Height"
            value={profile.height_cm ? `${profile.height_cm} cm` : "Not set"}
          />
          <Detail
            label="Weight"
            value={profile.weight_kg ? `${profile.weight_kg} kg` : "Not set"}
          />
          <Detail label="Blood group" value={profile.blood_group || "Not set"} />
          <Detail label="Diet" value={DIET_LABELS[profile.diet_type]} />
          <Detail label="Smoker" value={profile.smoker ? "Yes" : "No"} />
          <Detail label="Alcohol" value={profile.alcohol ? "Yes" : "No"} />
        </CardContent>
      </Card>

      <EditableSection
        title="Conditions"
        description="Long-term diagnoses. These feed into reasoning and medication safety."
        placeholder="e.g. Hypertension"
        draft={conditionDraft}
        setDraft={setConditionDraft}
        items={profile.conditions.map((c) => ({ id: c.id, label: c.condition_name }))}
        onAdd={() =>
          run(async () => {
            await api.post("/api/profile/conditions", {
              condition_name: conditionDraft.trim(),
              status: "active",
            });
            setConditionDraft("");
          })
        }
        onRemove={(id) => run(() => api.del(`/api/profile/conditions/${id}`))}
      />

      <EditableSection
        title="Allergies"
        description="Checked by drug class, so a penicillin allergy also flags amoxicillin."
        placeholder="e.g. Penicillin"
        draft={allergyDraft}
        setDraft={setAllergyDraft}
        items={profile.allergies.map((a) => ({
          id: a.id,
          label: a.allergen_class && a.allergen_class !== "other"
            ? `${a.allergen} (${a.allergen_class})`
            : a.allergen,
        }))}
        onAdd={() =>
          run(async () => {
            await api.post("/api/profile/allergies", {
              allergen: allergyDraft.trim(),
              allergen_class: "other",
            });
            setAllergyDraft("");
          })
        }
        onRemove={(id) => run(() => api.del(`/api/profile/allergies/${id}`))}
      />

      <EditableSection
        title="Medicines"
        description="Brand names are fine. Used for interaction and side-effect checks."
        placeholder="e.g. Crocin"
        draft={medDraft}
        setDraft={setMedDraft}
        items={profile.medications.map((m) => ({
          id: m.id,
          label: [m.brand_name || m.generic_name, m.dose].filter(Boolean).join(" - "),
        }))}
        onAdd={() =>
          run(async () => {
            await api.post("/api/profile/medications", {
              brand_name: medDraft.trim(),
              status: "prescribed_taking",
            });
            setMedDraft("");
          })
        }
        onRemove={(id) => run(() => api.del(`/api/profile/medications/${id}`))}
      />
    </Layout>
  );
}

const DIET_LABELS: Record<DietType, string> = {
  veg: "Vegetarian",
  non_veg: "Non-vegetarian",
  vegan: "Vegan",
  jain: "Jain",
};

function Detail({
  label,
  value,
  capitalize = false,
}: {
  label: string;
  value: string;
  capitalize?: boolean;
}) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={cn("mt-0.5 text-sm", capitalize && "capitalize")}>{value}</div>
    </div>
  );
}

function EditableSection({
  title,
  description,
  placeholder,
  draft,
  setDraft,
  items,
  onAdd,
  onRemove,
}: {
  title: string;
  description: string;
  placeholder: string;
  draft: string;
  setDraft: (v: string) => void;
  items: { id: number; label: string }[];
  onAdd: () => void;
  onRemove: (id: number) => void;
}) {
  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <Label className="sr-only" htmlFor={`add-${title}`}>
            Add to {title}
          </Label>
          <Input
            id={`add-${title}`}
            value={draft}
            placeholder={placeholder}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && draft.trim()) {
                e.preventDefault();
                onAdd();
              }
            }}
          />
          <Button variant="outline" onClick={onAdd} disabled={!draft.trim()}>
            <Plus className="h-4 w-4" />
            Add
          </Button>
        </div>

        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing recorded.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {items.map((item) => (
              <Badge key={item.id} variant="secondary" className="gap-1.5 py-1 pr-1.5">
                {item.label}
                <button
                  type="button"
                  onClick={() => onRemove(item.id)}
                  className="rounded-full p-0.5 hover:bg-background"
                  aria-label={`Remove ${item.label}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export type { ProfileOut };
