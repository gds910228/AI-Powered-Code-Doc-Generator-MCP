## To Do
- [ ] Create an 'AIService' for Tencent Hunyuan API to generate/enhance docstrings
- [ ] Implement 'Documentation' orchestrator to fill missing docstrings using AI
- [ ] Build 'SiteBuilder' with MkDocs + Material theme to generate static site
- [ ] Create main API endpoint `/api/v1/generate` end-to-end (wire services)
- [ ] Initialize the frontend (React + TypeScript + Tailwind)
- [ ] Build landing page UI (hero + repo URL form + features)
- [ ] Implement client call to `/api/v1/generate`
- [ ] Build Generation Status page (progress + result link)

## Doing
- [ ] Initialize backend with FastAPI (project skeleton, routes/services/utils structure)
  - [x] Create FastAPI app skeleton with CORS and health endpoint
  - [x] Add API skeleton file `app/api/v1/generate.py`
  - [x] Update dependencies in `pyproject.toml` (fastapi, uvicorn, pydantic)
  - [x] Mount API v1 router and connect `/api/v1/generate` to parser (local summary)

## Done
- [x] Create project plan and scope
- [x] Develop a 'Parser' service using Python's `ast` to extract modules/classes/functions and docstrings
