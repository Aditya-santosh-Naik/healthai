import { Link } from "react-router-dom";
import { AlertTriangle, MessageSquare, Pill, ShieldAlert } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Layout } from "@/components/Layout";
import { useAuth } from "@/lib/auth";

export default function Dashboard() {
  const { profile } = useAuth();
  if (!profile) return null;

  const activeConditions = profile.conditions.filter((c) => c.status === "active");
  const takenMeds = profile.medications.filter(
    (m) => m.status !== "prescribed_not_taking",
  );

  return (
    <Layout>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">
          Hello, {profile.name.split(" ")[0]}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Your profile is used on every consultation, so the reasoning is about you and
          not a generic patient.
        </p>
      </div>

      <Alert variant="warning" className="mb-8">
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription>
          If you have severe chest pain, trouble breathing, fainting, or heavy bleeding,
          stop and seek emergency care now. Do not use this app for an emergency.
        </AlertDescription>
      </Alert>

      <Card className="mb-8">
        <CardHeader>
          <CardTitle className="text-xl">Start a consultation</CardTitle>
          <CardDescription>
            Describe what you are feeling. The assistant asks targeted follow-up
            questions when the evidence is thin, rather than guessing.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild>
            <Link to="/consultation">
              <MessageSquare className="h-4 w-4" />
              New consultation
            </Link>
          </Button>
        </CardContent>
      </Card>

      <div className="grid gap-6 sm:grid-cols-3">
        <SummaryCard
          icon={<ShieldAlert className="h-4 w-4 text-primary" />}
          title="Conditions"
          items={activeConditions.map((c) => c.condition_name)}
          empty="None recorded"
        />
        <SummaryCard
          icon={<AlertTriangle className="h-4 w-4 text-primary" />}
          title="Allergies"
          items={profile.allergies.map((a) => a.allergen)}
          empty="None recorded"
        />
        <SummaryCard
          icon={<Pill className="h-4 w-4 text-primary" />}
          title="Medicines"
          items={takenMeds.map((m) => m.brand_name || m.generic_name || "Unnamed")}
          empty="None recorded"
        />
      </div>

      <p className="mt-6 text-sm text-muted-foreground">
        Something changed?{" "}
        <Link to="/profile" className="font-medium text-primary hover:underline">
          Update your profile
        </Link>
        .
      </p>
    </Layout>
  );
}

function SummaryCard({
  icon,
  title,
  items,
  empty,
}: {
  icon: React.ReactNode;
  title: string;
  items: string[];
  empty: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          {icon}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{empty}</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {items.map((item) => (
              <Badge key={item} variant="secondary">
                {item}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
