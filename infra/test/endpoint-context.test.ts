/**
 * Unit tests for `resolveEndpointContext`. The point of this test file
 * is to lock down the strict validation introduced after PR #144 left
 * `requireContext` with only a non-empty-string check — operators could
 * still pass `lol`, `http://localhost:3000`, or an empty entry and
 * synth would succeed.
 */

import {
  SYNTHETIC_CORS_ORIGINS,
  SYNTHETIC_IMAGES_CDN_BASE_URL,
  resolveEndpointContext,
} from "../lib/endpoint-context";

const validCors = "https://main.dew27gk9z09jh.amplifyapp.com";
const validImages =
  "https://grsv8u4uit.us-east-1.awsapprunner.com/local-images";

describe("resolveEndpointContext — happy path", () => {
  it("accepts a single https origin and a trailing-slash-stripped image base URL", () => {
    const resolved = resolveEndpointContext({
      corsOrigins: `${validCors}/`,
      imagesCdnBaseUrl: `${validImages}/`,
      allowSyntheticEndpoints: false,
    });
    expect(resolved.corsOrigins).toBe(validCors);
    expect(resolved.imagesCdnBaseUrl).toBe(validImages);
    expect(resolved.syntheticEndpointsUsed).toBe(false);
  });

  it("accepts and de-dupes a CSV list", () => {
    const resolved = resolveEndpointContext({
      corsOrigins: `${validCors},${validCors},https://other.example.com`,
      imagesCdnBaseUrl: validImages,
      allowSyntheticEndpoints: false,
    });
    expect(resolved.corsOrigins).toBe(
      `${validCors},https://other.example.com`,
    );
  });

  it("trims whitespace around CSV entries", () => {
    const resolved = resolveEndpointContext({
      corsOrigins: ` ${validCors} ,  https://other.example.com  `,
      imagesCdnBaseUrl: validImages,
      allowSyntheticEndpoints: false,
    });
    expect(resolved.corsOrigins).toBe(
      `${validCors},https://other.example.com`,
    );
  });
});

describe("resolveEndpointContext — missing values", () => {
  it("throws on missing cors_origins without the escape hatch", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: undefined,
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/Missing required context 'cors_origins'/);
  });

  it("throws on missing images_cdn_base_url without the escape hatch", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: validCors,
        imagesCdnBaseUrl: undefined,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/Missing required context 'images_cdn_base_url'/);
  });

  it("throws on empty string for cors_origins", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: "",
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/Missing required context 'cors_origins'/);
  });

  it("falls back to synthetic placeholders when escape hatch is on", () => {
    const resolved = resolveEndpointContext({
      corsOrigins: undefined,
      imagesCdnBaseUrl: undefined,
      allowSyntheticEndpoints: true,
    });
    expect(resolved.corsOrigins).toBe(SYNTHETIC_CORS_ORIGINS);
    expect(resolved.imagesCdnBaseUrl).toBe(SYNTHETIC_IMAGES_CDN_BASE_URL);
    expect(resolved.syntheticEndpointsUsed).toBe(true);
  });
});

describe("resolveEndpointContext — bad-shape values", () => {
  it("rejects a non-URL string", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: "lol",
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/is not a valid URL/);
  });

  it("rejects an http:// origin (must be https)", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: "http://app.example.com",
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/must use https/);
  });

  it("rejects a localhost origin", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: "https://localhost:3000",
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/loopback host/);
  });

  it("rejects a 127.0.0.1 origin", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: "https://127.0.0.1:3000",
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/loopback host/);
  });

  it("rejects an empty CSV entry between commas", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: `${validCors},,https://other.example.com`,
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/is empty/);
  });

  it("rejects a non-URL images_cdn_base_url", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: validCors,
        imagesCdnBaseUrl: "lol",
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/is not a valid URL/);
  });

  it("rejects an http:// images_cdn_base_url", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: validCors,
        imagesCdnBaseUrl: "http://api.example.com/local-images",
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/must use https/);
  });

  it("rejects a localhost images_cdn_base_url", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: validCors,
        imagesCdnBaseUrl: "https://localhost:8000/local-images",
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/loopback host/);
  });
});

describe("resolveEndpointContext — .invalid TLD policy", () => {
  it("rejects a .invalid cors origin without the escape hatch", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: "https://something.invalid",
        imagesCdnBaseUrl: validImages,
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/'.invalid' TLD/);
  });

  it("rejects a .invalid images_cdn_base_url without the escape hatch", () => {
    expect(() =>
      resolveEndpointContext({
        corsOrigins: validCors,
        imagesCdnBaseUrl: "https://something.invalid/local-images",
        allowSyntheticEndpoints: false,
      }),
    ).toThrow(/'.invalid' TLD/);
  });

  it("accepts .invalid values when the escape hatch is on (bootstrap mode)", () => {
    const resolved = resolveEndpointContext({
      corsOrigins: "https://bootstrap.invalid",
      imagesCdnBaseUrl: "https://bootstrap.invalid/local-images",
      allowSyntheticEndpoints: true,
    });
    expect(resolved.corsOrigins).toBe("https://bootstrap.invalid");
    expect(resolved.imagesCdnBaseUrl).toBe(
      "https://bootstrap.invalid/local-images",
    );
    // Operator-supplied placeholders are still flagged as synthetic
    // because they match the canonical synthetic values, exposing the
    // CDK warning + stack tag downstream.
    expect(resolved.syntheticEndpointsUsed).toBe(false);
  });

  it("sets syntheticEndpointsUsed when the resolver itself filled in placeholders", () => {
    const resolved = resolveEndpointContext({
      corsOrigins: undefined,
      imagesCdnBaseUrl: validImages,
      allowSyntheticEndpoints: true,
    });
    expect(resolved.corsOrigins).toBe(SYNTHETIC_CORS_ORIGINS);
    expect(resolved.syntheticEndpointsUsed).toBe(true);
  });
});
