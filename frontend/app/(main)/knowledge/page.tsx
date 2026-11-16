import { connection } from "next/server";

import { KnowledgeView } from "@/components/knowledge/knowledge-view";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";

/**
 * Knowledge Base. The document list is fetched on the server so the page arrives filled in;
 * the client view then handles uploads and polls for ingestion progress.
 */
export default async function KnowledgePage() {
  await connection(); // per-request data: never prerender
  const [documents, config] = await Promise.all([api.documents(), api.knowledgeConfig()]);
  return (
    <>
      <PageHeader title="Knowledge Base" />
      <KnowledgeView initialDocuments={documents} config={config} />
    </>
  );
}
