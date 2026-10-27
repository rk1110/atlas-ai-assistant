import { BookOpen } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { PagePlaceholder } from "@/components/page-placeholder";

export default function KnowledgePage() {
  return (
    <>
      <PageHeader title="Knowledge Base" />
      <PagePlaceholder
        icon={BookOpen}
        phase={2}
        title="Your company's documents, searchable"
        summary="Atlas will read the GitLab handbook and the Acme Corp docs, split them into passages, and answer with citations you can click."
        features={[
          "Drag-and-drop upload for PDF, HTML and Markdown",
          "Live ingestion progress for each document",
          "Chunk viewer: see exactly what Atlas retrieves",
          "Embedding map of documents clustered by topic (Phase 3)",
        ]}
      />
    </>
  );
}
