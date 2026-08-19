import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Activity, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { DisclaimerBar } from "@/components/Layout";
import { api } from "@/api/client";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import type {
  AllergyIn,
  ConditionIn,
  DietType,
  MedicationIn,
  ProfileOut,
  Sex,
} from "@/api/types";

const STEPS = ["About you", "Conditions", "Allergies", "Medications"];

const BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"];

// Allergen classes drive cross-reactivity: a penicillin allergy must flag
// amoxicillin, an NSAID allergy must flag ibuprofen and diclofenac.
const ALLERGEN_CLASSES = [
  { value: "penicillin", label: "Penicillin group" },
  { value: "cephalosporin", label: "Cephalosporin group" },
  { value: "nsaid", label: "Painkillers (NSAIDs)" },
  { value: "sulfonamide", label: "Sulfa drugs" },
  { value: "macrolide", label: "Macrolides" },
  { value: "food", label: "Food" },
  { value: "other", label: "Other / not sure" },
];

export default function Onboarding() {
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Step 1
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [sex, setSex] = useState<Sex | "">("");
  const [heightCm, setHeightCm] = useState("");
  const [weightKg, setWeightKg] = useState("");
  const [bloodGroup, setBloodGroup] = useState("");
  const [dietType, setDietType] = useState<DietType>("veg");
  const [smoker, setSmoker] = useState(false);
  const [alcohol, setAlcohol] = useState(false);

  // Steps 2-4
  const [conditions, setConditions] = useState<ConditionIn[]>([]);
  const [conditionDraft, setConditionDraft] = useState("");

  const [allergies, setAllergies] = useState<AllergyIn[]>([]);
  const [allergyDraft, setAllergyDraft] = useState("");
  const [allergyClass, setAllergyClass] = useState("other");
  const [allergyReaction, setAllergyReaction] = useState("");

  const [medications, setMedications] = useState<MedicationIn[]>([]);
  const [medBrand, setMedBrand] = useState("");
  const [medDose, setMedDose] = useState("");
  const [medFrequency, setMedFrequency] = useState("");

  const { refreshProfile } = useAuth();
  const navigate = useNavigate();

  const ageNumber = Number(age);
  const step1Valid =
    name.trim().length > 0 && Number.isFinite(ageNumber) && ageNumber >= 18 && sex !== "";

  function addCondition() {
    const value = conditionDraft.trim();
    if (!value) return;
    setConditions([...conditions, { condition_name: value, status: "active" }]);
    setConditionDraft("");
  }

  function addAllergy() {
    const value = allergyDraft.trim();
    if (!value) return;
    setAllergies([
      ...allergies,
      {
        allergen: value,
        allergen_class: allergyClass,
        reaction: allergyReaction.trim() || null,
      },
    ]);
    setAllergyDraft("");
    setAllergyReaction("");
    setAllergyClass("other");
  }

  function addMedication() {
    const value = medBrand.trim();
    if (!value) return;
    setMedications([
      ...medications,
      {
        brand_name: value,
        dose: medDose.trim() || null,
        frequency: medFrequency.trim() || null,
        route: "oral",
        status: "prescribed_taking",
      },
    ]);
    setMedBrand("");
    setMedDose("");
    setMedFrequency("");
  }

  async function handleSubmit() {
    setError(null);
    setBusy(true);
    try {
      await api.post<ProfileOut>("/api/profile", {
        name: name.trim(),
        age: ageNumber,
        sex,
        height_cm: heightCm ? Number(heightCm) : null,
        weight_kg: weightKg ? Number(weightKg) : null,
        blood_group: bloodGroup || null,
        diet_type: dietType,
        smoker,
        alcohol,
        conditions,
        allergies,
        medications,
      });
      await refreshProfile();
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save your profile");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-muted/30">
      <div className="flex flex-1 justify-center px-6 py-12">
        <div className="w-full max-w-2xl">
          <div className="mb-8 flex items-center gap-2 text-lg font-semibold tracking-tight">
            <Activity className="h-5 w-5 text-primary" />
            Set up your health profile
          </div>

          {/* Step indicator */}
          <div className="mb-8 flex items-center gap-2">
            {STEPS.map((label, i) => (
              <div key={label} className="flex flex-1 flex-col gap-2">
                <div
                  className={cn(
                    "h-1 rounded-full transition-colors",
                    i <= step ? "bg-primary" : "bg-border",
                  )}
                />
                <span
                  className={cn(
                    "text-xs",
                    i === step ? "font-medium text-foreground" : "text-muted-foreground",
                  )}
                >
                  {label}
                </span>
              </div>
            ))}
          </div>

          <Card>
            {step === 0 && (
              <>
                <CardHeader>
                  <CardTitle className="text-xl">About you</CardTitle>
                  <CardDescription>
                    This lets the assistant reason about your situation rather than a
                    generic one. HealthAI is for adults only.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="name">Full name</Label>
                    <Input
                      id="name"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Your name"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="age">Age</Label>
                      <Input
                        id="age"
                        type="number"
                        min={18}
                        max={120}
                        value={age}
                        onChange={(e) => setAge(e.target.value)}
                        placeholder="e.g. 34"
                      />
                      {age !== "" && ageNumber < 18 && (
                        <p className="text-xs text-destructive">
                          HealthAI does not assess anyone under 18. Please see a doctor
                          or paediatrician.
                        </p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <Label>Sex</Label>
                      <Select value={sex} onValueChange={(v) => setSex(v as Sex)}>
                        <SelectTrigger>
                          <SelectValue placeholder="Select" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="male">Male</SelectItem>
                          <SelectItem value="female">Female</SelectItem>
                          <SelectItem value="other">Other</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="height">Height (cm)</Label>
                      <Input
                        id="height"
                        type="number"
                        value={heightCm}
                        onChange={(e) => setHeightCm(e.target.value)}
                        placeholder="170"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="weight">Weight (kg)</Label>
                      <Input
                        id="weight"
                        type="number"
                        value={weightKg}
                        onChange={(e) => setWeightKg(e.target.value)}
                        placeholder="65"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Blood group</Label>
                      <Select value={bloodGroup} onValueChange={setBloodGroup}>
                        <SelectTrigger>
                          <SelectValue placeholder="Optional" />
                        </SelectTrigger>
                        <SelectContent>
                          {BLOOD_GROUPS.map((g) => (
                            <SelectItem key={g} value={g}>
                              {g}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label>Diet</Label>
                    <Select
                      value={dietType}
                      onValueChange={(v) => setDietType(v as DietType)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="veg">Vegetarian</SelectItem>
                        <SelectItem value="non_veg">Non-vegetarian</SelectItem>
                        <SelectItem value="vegan">Vegan</SelectItem>
                        <SelectItem value="jain">Jain</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      Dietary advice is filtered against this, so a vegetarian is never
                      told to eat chicken soup.
                    </p>
                  </div>

                  <div className="flex gap-6 pt-2">
                    <label className="flex items-center gap-2 text-sm">
                      <Checkbox
                        checked={smoker}
                        onCheckedChange={(v) => setSmoker(v === true)}
                      />
                      I smoke
                    </label>
                    <label className="flex items-center gap-2 text-sm">
                      <Checkbox
                        checked={alcohol}
                        onCheckedChange={(v) => setAlcohol(v === true)}
                      />
                      I drink alcohol
                    </label>
                  </div>
                </CardContent>
              </>
            )}

            {step === 1 && (
              <>
                <CardHeader>
                  <CardTitle className="text-xl">Ongoing conditions</CardTitle>
                  <CardDescription>
                    Anything you have been diagnosed with, such as diabetes, high blood
                    pressure or asthma. Leave empty if none.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex gap-2">
                    <Input
                      value={conditionDraft}
                      onChange={(e) => setConditionDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          addCondition();
                        }
                      }}
                      placeholder="e.g. Hypertension"
                    />
                    <Button type="button" variant="outline" onClick={addCondition}>
                      <Plus className="h-4 w-4" />
                      Add
                    </Button>
                  </div>

                  <ItemList
                    items={conditions.map((c) => c.condition_name)}
                    onRemove={(i) => setConditions(conditions.filter((_, j) => j !== i))}
                    empty="No conditions added."
                  />
                </CardContent>
              </>
            )}

            {step === 2 && (
              <>
                <CardHeader>
                  <CardTitle className="text-xl">Allergies</CardTitle>
                  <CardDescription>
                    Medicine and food allergies. The group matters: a penicillin allergy
                    also flags related antibiotics like amoxicillin.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="allergen">Allergen</Label>
                      <Input
                        id="allergen"
                        value={allergyDraft}
                        onChange={(e) => setAllergyDraft(e.target.value)}
                        placeholder="e.g. Penicillin"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Group</Label>
                      <Select value={allergyClass} onValueChange={setAllergyClass}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {ALLERGEN_CLASSES.map((c) => (
                            <SelectItem key={c.value} value={c.value}>
                              {c.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="reaction">What happens? (optional)</Label>
                    <Input
                      id="reaction"
                      value={allergyReaction}
                      onChange={(e) => setAllergyReaction(e.target.value)}
                      placeholder="e.g. Rash, swelling"
                    />
                  </div>

                  <Button type="button" variant="outline" onClick={addAllergy}>
                    <Plus className="h-4 w-4" />
                    Add allergy
                  </Button>

                  <ItemList
                    items={allergies.map(
                      (a) =>
                        `${a.allergen}${a.allergen_class && a.allergen_class !== "other" ? ` (${a.allergen_class})` : ""}`,
                    )}
                    onRemove={(i) => setAllergies(allergies.filter((_, j) => j !== i))}
                    empty="No allergies added."
                  />
                </CardContent>
              </>
            )}

            {step === 3 && (
              <>
                <CardHeader>
                  <CardTitle className="text-xl">Current medicines</CardTitle>
                  <CardDescription>
                    Brand names are fine -- Crocin, Dolo, Combiflam, Pan-D. These are
                    checked for interactions against anything discussed later.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid gap-3 sm:grid-cols-3">
                    <div className="space-y-2">
                      <Label htmlFor="med">Medicine</Label>
                      <Input
                        id="med"
                        value={medBrand}
                        onChange={(e) => setMedBrand(e.target.value)}
                        placeholder="e.g. Amlong"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="dose">Dose</Label>
                      <Input
                        id="dose"
                        value={medDose}
                        onChange={(e) => setMedDose(e.target.value)}
                        placeholder="e.g. 5 mg"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="freq">How often</Label>
                      <Input
                        id="freq"
                        value={medFrequency}
                        onChange={(e) => setMedFrequency(e.target.value)}
                        placeholder="e.g. once daily"
                      />
                    </div>
                  </div>

                  <Button type="button" variant="outline" onClick={addMedication}>
                    <Plus className="h-4 w-4" />
                    Add medicine
                  </Button>

                  <ItemList
                    items={medications.map((m) =>
                      [m.brand_name, m.dose, m.frequency].filter(Boolean).join(" - "),
                    )}
                    onRemove={(i) => setMedications(medications.filter((_, j) => j !== i))}
                    empty="No medicines added."
                  />

                  {error && (
                    <Alert variant="destructive">
                      <AlertDescription>{error}</AlertDescription>
                    </Alert>
                  )}
                </CardContent>
              </>
            )}
          </Card>

          <div className="mt-6 flex items-center justify-between">
            <Button
              variant="ghost"
              onClick={() => setStep(step - 1)}
              disabled={step === 0 || busy}
            >
              Back
            </Button>

            {step < STEPS.length - 1 ? (
              <Button
                onClick={() => setStep(step + 1)}
                disabled={step === 0 && !step1Valid}
              >
                Continue
              </Button>
            ) : (
              <Button onClick={handleSubmit} disabled={busy}>
                {busy ? "Saving..." : "Finish setup"}
              </Button>
            )}
          </div>
        </div>
      </div>

      <DisclaimerBar />
    </div>
  );
}

function ItemList({
  items,
  onRemove,
  empty,
}: {
  items: string[];
  onRemove: (index: number) => void;
  empty: string;
}) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">{empty}</p>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((label, i) => (
        <Badge key={`${label}-${i}`} variant="secondary" className="gap-1.5 py-1 pr-1.5">
          {label}
          <button
            type="button"
            onClick={() => onRemove(i)}
            className="rounded-full p-0.5 hover:bg-background"
            aria-label={`Remove ${label}`}
          >
            <X className="h-3 w-3" />
          </button>
        </Badge>
      ))}
    </div>
  );
}
