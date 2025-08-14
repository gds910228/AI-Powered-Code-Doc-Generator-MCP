# AI Agent Orchestration & Debugging Platform

## Core Features

- Visual, node-based workflow editor for creating multi-agent systems.

- Real-time monitoring of agent states and data flow on a live dashboard.

- Interactive debugging console to pause, inspect, and control workflow execution.

## Tech Stack

{
  "Backend": "Python with the FastAPI framework for REST and WebSocket APIs.",
  "Frontend": {
    "arch": "react",
    "component": "shadcn"
  },
  "Database": "Supabase (PostgreSQL) for data persistence and real-time features."
}

## Design

A modern and professional developer tool UI using a Glassmorphism Tech Blue style. The design prioritizes clarity and functionality with a node-based visual editor, clean dashboards, and translucent interface elements to create a focused, high-tech user experience.

## Plan

Note: 

- [ ] is holding
- [/] is doing
- [X] is done

---

[ ] Initialize the FastAPI backend project, setting up the basic file structure and dependencies.

[ ] Define the core data models (Workflow, AgentNode, ExecutionLog) using Pydantic and set up corresponding tables in Supabase.

[ ] Implement the RESTful API endpoints for CRUD (Create, Read, Update, Delete) operations on workflows.

[ ] Set up the WebSocket endpoint in FastAPI to handle real-time communication for logging and state updates.

[ ] Initialize the React frontend project using Vite with TypeScript and configure `shadcn/ui`.

[ ] Build the static UI layout for the Workflow Editor page, including the three main panels (Toolbox, Canvas, Inspector) using `shadcn/ui` components.

[ ] Integrate a library like `React Flow` into the central canvas to enable draggable nodes and connectable edges.

[ ] Connect the frontend to the backend API to fetch, display, and save workflow configurations.

[ ] Implement the client-side WebSocket logic to connect to the backend and display real-time logs in the console.

[ ] Enhance the visualizer to reflect agent state changes (e.g., active, success, error) based on data received from the WebSocket.

[ ] Implement the backend logic for the agent execution engine, which interprets the workflow graph and emits state updates via WebSockets.

[ ] Add interactive debugging controls to the frontend that send commands (pause, step, resume) to the backend via the WebSocket connection.
