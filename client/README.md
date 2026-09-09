# CinemAgent client

The CinemAgent client is a SvelteKit + TypeScript workspace for writing and navigating stories as narrative graphs. It uses Tailwind CSS, shadcn-svelte, Tiptap, and Svelte Flow.

For the product overview, architecture, and full API/worker setup, see the [project documentation](../documentation/README.md).

## Local development

1. Ensure the FastAPI service is running on port `8080` and has access to ClickHouse.
2. Create `.env` from `.env.example` and provide the server-side API configuration:

   ```dotenv
   FASTAPI_URL=http://localhost:8080
   NARRATIVE_API_KEY=replace-with-the-backend-api-key
   ```

3. Install dependencies and start Vite:

   ```powershell
   pnpm install
   pnpm dev
   ```

The application is normally available at [http://localhost:5173](http://localhost:5173). The browser calls same-origin `/api` routes; SvelteKit forwards those routes to FastAPI and keeps `NARRATIVE_API_KEY` on the server.

## Checks

```powershell
pnpm check
pnpm lint
pnpm test
pnpm build
```
