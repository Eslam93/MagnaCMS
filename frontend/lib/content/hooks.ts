"use client";

import { useMutation } from "@tanstack/react-query";

import { api } from "@/lib/api";

import type { GenerateInput } from "@/lib/validation/generate";
import type { components } from "@/types/api";

export type GenerateResponse = components["schemas"]["GenerateResponse"];

type ErrorEnvelope = components["schemas"]["ErrorEnvelope"];

const FRIENDLY_MESSAGES: Record<string, string> = {
  UNSUPPORTED_CONTENT_TYPE: "That content type isn't available yet — Slice 2 widens this.",
  VALIDATION_FAILED: "Some fields don't look right — check the form.",
  RATE_LIMITED: "You've hit the per-minute generate limit. Wait a minute and try again.",
  MISSING_TOKEN: "Your session has expired. Sign in again.",
  TOKEN_EXPIRED: "Your session has expired. Sign in again.",
  INVALID_TOKEN: "Your session has expired. Sign in again.",
};

export function generateErrorMessage(
  body: unknown,
  fallback = "Something went wrong generating content. Try again.",
): string {
  const envelope = body as ErrorEnvelope | undefined;
  if (!envelope?.error) return fallback;
  return FRIENDLY_MESSAGES[envelope.error.code] ?? envelope.error.message ?? fallback;
}

/**
 * Submit a generate request. The mutation's `data` is the full
 * GenerateResponse — caller renders `result` if non-null, or shows a
 * fallback-mode banner with `rendered_text` when result_parse_status
 * is "failed".
 */
export function useGenerateMutation() {
  return useMutation<GenerateResponse, Error, GenerateInput>({
    mutationFn: async (input) => {
      // Convert empty-string optionals to undefined so the backend sees
      // an absent field rather than a "" that would fail max_length=0.
      const body = {
        content_type: input.content_type,
        topic: input.topic.trim(),
        tone: input.tone?.trim() ? input.tone.trim() : undefined,
        target_audience: input.target_audience?.trim() ? input.target_audience.trim() : undefined,
      };
      const { data, error, response } = await api.POST("/content/generate", {
        body,
      });
      if (error || !data) {
        throw new Error(generateErrorMessage(error, response.statusText));
      }
      return data;
    },
  });
}
