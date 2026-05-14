/**
 * Hand-stubbed OpenAPI schema for the MagnaCMS backend.
 *
 * Regenerate from the live spec with `pnpm gen:api` once the API is
 * deployed (P2.7+). For now this stub matches the endpoints that
 * exist as of P1.9: register, login, refresh, logout, me, health.
 *
 * Keep this file in sync with the backend until automated generation
 * kicks in.
 */

export interface paths {
  "/auth/register": {
    post: operations["register"];
  };
  "/auth/login": {
    post: operations["login"];
  };
  "/auth/refresh": {
    post: operations["refresh"];
  };
  "/auth/logout": {
    post: operations["logout"];
  };
  "/auth/me": {
    get: operations["me"];
  };
  "/health": {
    get: operations["health"];
  };
}

export interface components {
  schemas: {
    User: {
      id: string;
      email: string;
      full_name: string;
      email_verified_at: string | null;
      last_login_at: string | null;
      created_at: string;
    };
    AuthResponse: {
      user: components["schemas"]["User"];
      access_token: string;
      token_type: "Bearer";
      expires_in: number;
    };
    RegisterRequest: {
      email: string;
      password: string;
      full_name: string;
    };
    LoginRequest: {
      email: string;
      password: string;
    };
    ErrorEnvelope: {
      error: {
        code: string;
        message: string;
        details: Record<string, unknown>;
      };
      meta: {
        request_id: string | null;
      };
    };
  };
}

export interface operations {
  register: {
    requestBody: {
      content: {
        "application/json": components["schemas"]["RegisterRequest"];
      };
    };
    responses: {
      201: {
        content: {
          "application/json": components["schemas"]["AuthResponse"];
        };
      };
      409: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      422: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  login: {
    requestBody: {
      content: {
        "application/json": components["schemas"]["LoginRequest"];
      };
    };
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["AuthResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  refresh: {
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["AuthResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  logout: {
    responses: {
      204: { content: never };
    };
  };
  me: {
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["User"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  health: {
    responses: {
      200: {
        content: {
          "application/json": {
            status: string;
            version: string;
            environment: string;
            dependencies: Record<string, string>;
          };
        };
      };
    };
  };
}
