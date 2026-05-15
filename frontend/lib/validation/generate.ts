/**
 * Zod schema for the /generate form. Mirrors the backend Pydantic
 * GenerateRequest constraints (see backend/app/schemas/content.py) so
 * the client gets immediate inline validation while the backend remains
 * the source of truth.
 */

import { z } from "zod";

import type { components } from "@/types/api";

type ContentType = components["schemas"]["ContentType"];

/**
 * Content types the form offers. Slice 1 enables blog_post only;
 * the other entries render disabled with a tooltip so the UI doesn't
 * change shape when Slice 2 widens support.
 */
export const CONTENT_TYPE_OPTIONS: ReadonlyArray<{
  value: ContentType;
  label: string;
  enabled: boolean;
  tooltip?: string;
}> = [
  { value: "blog_post", label: "Blog post", enabled: true },
  {
    value: "linkedin_post",
    label: "LinkedIn post",
    enabled: false,
    tooltip: "Coming in Slice 2",
  },
  {
    value: "email",
    label: "Email",
    enabled: false,
    tooltip: "Coming in Slice 2",
  },
  {
    value: "ad_copy",
    label: "Ad copy",
    enabled: false,
    tooltip: "Coming in Slice 2",
  },
];

export const generateSchema = z.object({
  content_type: z.enum(["blog_post", "linkedin_post", "ad_copy", "email"]),
  topic: z
    .string()
    .trim()
    .min(3, "Topic needs at least 3 characters")
    .max(500, "Topic must be 500 characters or fewer"),
  tone: z
    .string()
    .trim()
    .max(120, "Tone must be 120 characters or fewer")
    .optional()
    .or(z.literal("")),
  target_audience: z
    .string()
    .trim()
    .max(500, "Audience must be 500 characters or fewer")
    .optional()
    .or(z.literal("")),
});

export type GenerateInput = z.infer<typeof generateSchema>;
