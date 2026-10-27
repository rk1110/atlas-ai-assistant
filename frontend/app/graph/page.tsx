import { Network } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { PagePlaceholder } from "@/components/page-placeholder";

export default function GraphPage() {
  return (
    <>
      <PageHeader title="Knowledge Graph" />
      <PagePlaceholder
        icon={Network}
        phase={3}
        title="How people, teams and policies connect"
        summary="Atlas will extract entities from the documents into a graph, so it can answer questions that span several documents."
        features={[
          "Zoomable graph of teams, people and policies",
          "Click a node to see the documents that mention it",
          "GraphRAG: answers that follow links between documents",
          "Compare graph answers with plain search in the evals",
        ]}
      />
    </>
  );
}
