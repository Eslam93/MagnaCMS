"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";

import { ImagePanel } from "@/components/features/image-panel";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";

import { useContentDetailQuery } from "@/lib/content/hooks";

interface Props {
  contentId: string | null;
  onClose: () => void;
}

/**
 * Modal that fetches and renders one content piece in full.
 *
 * `contentId === null` means "closed". The query is gated on the id so
 * it doesn't fire while the modal is hidden. Copy reaches into the
 * detail's `rendered_text` so what the user sees is exactly what they
 * paste.
 */
export function ContentDetailDialog({ contentId, onClose }: Props) {
  const open = contentId !== null;
  const detail = useContentDetailQuery(contentId);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!detail.data) return;
    try {
      await navigator.clipboard.writeText(detail.data.rendered_text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard refused — text is still visible */
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={detail.data?.topic ?? "Loading…"}
      data-testid="content-detail-dialog"
    >
      {detail.isPending ? (
        <p className="text-sm text-muted-foreground">Loading content…</p>
      ) : detail.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {detail.error.message}
        </p>
      ) : detail.data ? (
        <div className="space-y-4">
          <header className="flex items-center justify-between gap-4 text-xs text-muted-foreground">
            <div>
              <span className="font-mono">{detail.data.model_id}</span>
              {" · "}
              <span>{detail.data.word_count} words</span>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleCopy}
              data-testid="content-detail-copy"
            >
              {copied ? "Copied" : "Copy"}
            </Button>
          </header>

          {detail.data.result_parse_status === "failed" ? (
            <p
              className="rounded-md border border-amber-500/40 bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200"
              role="status"
            >
              Generated in fallback mode — formatting may be inconsistent. The raw model output is
              shown below.
            </p>
          ) : null}

          <div
            className="prose prose-sm dark:prose-invert max-w-none"
            data-testid="content-detail-body"
          >
            {detail.data.result_parse_status === "failed" ? (
              <pre className="overflow-auto whitespace-pre-wrap text-sm">
                {detail.data.rendered_text}
              </pre>
            ) : (
              <ReactMarkdown>{detail.data.rendered_text}</ReactMarkdown>
            )}
          </div>

          <ImagePanel
            contentId={detail.data.id}
            disabled={detail.data.result_parse_status === "failed"}
          />
        </div>
      ) : null}
    </Modal>
  );
}
