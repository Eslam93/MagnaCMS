"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { generateErrorMessage } from "@/lib/content/hooks";

import type { components } from "@/types/api";

export type GeneratedImage = components["schemas"]["GeneratedImage"];
export type ImageListResponse = components["schemas"]["ImageListResponse"];
export type ImageStyle = components["schemas"]["ImageStyle"];

export const IMAGE_STYLES: ReadonlyArray<{ value: ImageStyle; label: string }> = [
  { value: "photorealistic", label: "Photorealistic" },
  { value: "illustration", label: "Illustration" },
  { value: "minimalist", label: "Minimalist" },
  { value: "3d_render", label: "3D render" },
  { value: "watercolor", label: "Watercolor" },
  { value: "cinematic", label: "Cinematic" },
];

/**
 * List every image version generated for a content piece, newest
 * first. Gated on the content id so the hook is safe to call with
 * `null` (the query won't fire).
 */
export function useImageListQuery(contentId: string | null) {
  return useQuery<ImageListResponse, Error>({
    queryKey: ["content", "images", contentId],
    enabled: Boolean(contentId),
    queryFn: async () => {
      const { data, error, response } = await api.GET("/content/{content_id}/images", {
        params: { path: { content_id: contentId as string } },
      });
      if (error || !data) {
        throw new Error(generateErrorMessage(error, response.statusText));
      }
      return data;
    },
  });
}

export interface ImageGenerateInput {
  contentId: string;
  style: ImageStyle;
}

/**
 * Generate (or regenerate) the image for a content piece. The success
 * payload is the new image row; we invalidate the per-piece image
 * list so the panel re-fetches and surfaces the new "current".
 */
export function useImageGenerateMutation() {
  const queryClient = useQueryClient();
  return useMutation<GeneratedImage, Error, ImageGenerateInput>({
    mutationFn: async ({ contentId, style }) => {
      const { data, error, response } = await api.POST("/content/{content_id}/image", {
        params: { path: { content_id: contentId } },
        body: { style },
      });
      if (error || !data) {
        throw new Error(generateErrorMessage(error, response.statusText));
      }
      return data.image;
    },
    onSuccess: (_image, { contentId }) => {
      queryClient.invalidateQueries({ queryKey: ["content", "images", contentId] });
    },
  });
}
