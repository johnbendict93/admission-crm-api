/**
 * Orval config: reads the live OpenAPI schema exported from the running
 * FastAPI app (../openapi.json, generated via `app.openapi()` - see
 * README in this folder) and emits typed models + React Query hooks per
 * endpoint. Regenerate any time the backend schema changes:
 *   npm run generate
 */
module.exports = {
  admissionCrm: {
    input: '../openapi.json',
    output: {
      mode: 'tags-split',
      target: './src/generated/endpoints.ts',
      schemas: './src/generated/models',
      client: 'react-query',
      httpClient: 'fetch',
      override: {
        query: {
          version: 5,
        },
        mutator: {
          path: './src/api-mutator.ts',
          name: 'apiFetch',
        },
      },
    },
  },
};
