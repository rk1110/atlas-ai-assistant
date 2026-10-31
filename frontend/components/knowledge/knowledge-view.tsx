"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { ChunkViewer } from "@/components/knowledge/chunk-viewer";
import { DocumentTable } from "@/components/knowledge/document-table";
import { EmbeddingMap } from "@/components/knowledge/embedding-map";
import { KnowledgeStats } from "@/components/knowledge/knowledge-stats";
import { RetrievalTester } from "@/components/knowledge/retrieval-tester";
import { UploadDropzone } from "@/components/knowledge/upload-dropzone";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { api, type KnowledgeConfig, type KnowledgeDocument } from "@/lib/api";

const POLL_MS = 1000;

/**
 * The Knowledge Base page: what Atlas knows, uploads, and a look inside retrieval.
 *
 * Progress works by polling: an upload returns at once with status "pending", the backend
 * ingests it in the background, and while any document is pending or processing this view
 * re-fetches the list every second. Polling is the simplest option that works everywhere;
 * pushing updates (SSE, like the chat) is the upgrade if lists get large.
 */
export function KnowledgeView({ initialDocuments, config }: { initialDocuments: KnowledgeDocument[]; config: KnowledgeConfig }) {
  const [documents, setDocuments] = useState(initialDocuments);
  const [uploading, setUploading] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<KnowledgeDocument | null>(null);
  const [highlighted, setHighlighted] = useState<string[]>([]);

  const refresh = useCallback(async () => {
    try {
      setDocuments(await api.documents());
    } catch {
      // keep showing the last list; the next poll or action tries again
    }
  }, []);

  const busy = documents.some((d) => d.status === "pending" || d.status === "processing");
  useEffect(() => {
    if (!busy) return;
    const timer = setTimeout(refresh, POLL_MS);
    return () => clearTimeout(timer);
  }, [busy, documents, refresh]);

  const upload = async (files: File[]) => {
    setUploading(true);
    for (const file of files) {
      try {
        await api.upload(file);
        toast.success(`${file.name} uploaded`, { description: "Parsing, chunking and embedding…" });
      } catch (e) {
        toast.error(`${file.name} was not uploaded`, { description: e instanceof Error ? e.message : undefined });
      }
    }
    setUploading(false);
    await refresh();
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    try {
      await api.deleteDocument(pendingDelete.id);
      toast.success(`${pendingDelete.title} deleted`);
    } catch (e) {
      toast.error("Delete failed", { description: e instanceof Error ? e.message : undefined });
    }
    setPendingDelete(null);
    await refresh();
  };

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-8 px-4 py-6">
      <KnowledgeStats documents={documents} embeddingModel={config.embedding_model} />
      <RetrievalTester
        strategies={config.strategies}
        defaultStrategy={config.default_strategy}
        onOpenDocument={setOpenId}
        onResults={setHighlighted}
      />
      <EmbeddingMap highlighted={highlighted} onOpenDocument={setOpenId} />
      <section className="flex flex-col gap-3">
        <div>
          <h2 className="text-sm font-medium">Upload</h2>
          <p className="text-xs text-muted-foreground">Uploaded files become searchable in the chat, with citations.</p>
        </div>
        <UploadDropzone extensions={config.upload_extensions} maxFileMb={config.max_file_mb} uploading={uploading} onFiles={upload} />
      </section>
      <DocumentTable documents={documents} uploadSource={config.upload_source} onOpen={setOpenId} onDelete={setPendingDelete} />
      <ChunkViewer documentId={openId} onClose={() => setOpenId(null)} />
      <AlertDialog open={pendingDelete !== null} onOpenChange={(open) => !open && setPendingDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {pendingDelete?.title}?</AlertDialogTitle>
            <AlertDialogDescription>
              The file and its {pendingDelete?.chunk_count} chunks are removed. Atlas can no longer cite it.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={confirmDelete}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
