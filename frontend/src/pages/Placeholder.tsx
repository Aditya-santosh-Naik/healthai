import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Layout } from "@/components/Layout";

/**
 * Routes that exist so navigation is complete on Day 1. Days 3-6 replace these
 * with the real consultation, history and document screens.
 */
export function Placeholder({ title, description }: { title: string; description: string }) {
  return (
    <Layout>
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Not built yet. This screen arrives later in the build.
          </p>
        </CardContent>
      </Card>
    </Layout>
  );
}

export const ConsultationPage = () => (
  <Placeholder
    title="Consultation"
    description="Symptom intake, follow-up questions and the structured assessment."
  />
);

export const HistoryPage = () => (
  <Placeholder
    title="History"
    description="Your past consultations and their assessments."
  />
);

export const DocumentsPage = () => (
  <Placeholder
    title="Documents"
    description="Upload a text-layer PDF report; extracted facts are confirmed by you before they reach your profile."
  />
);
