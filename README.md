# Meeting Intelligence Engine

A multi agent system that takes a recorded meeting and turns it into something actually useful: a clean transcript, a list of action items, key decisions, and a short summary of what happened. The goal is to save people from re watching an hour long call just to remember what was agreed on.

## What it does

You upload a meeting recording. The system transcribes it using Whisper, then runs a set of agents on top of that transcript to pull out structured information. Right now that includes:

- Transcription with speaker segments
- Action items, so you know who is doing what
- A timeline of what was discussed and when
- Key decisions that were made during the call
- A short set of insights summarizing the meeting

Each of these is handled by its own agent, built on a shared base class that takes care of retries, timeouts, and basic guardrails so one failing agent does not take down the whole pipeline.

## Why I built this

I wanted a project that goes beyond a simple wrapper around an LLM call. This one deals with real production concerns: async job handling, structured logging, error recovery, and a system design that can scale past a single script. It is also something I actually plan to use myself once the core features are working.

## Tech stack

Backend is built with FastAPI and Python. Agent orchestration is done with LangChain, and the LLM layer can run either locally through Ollama or against the Anthropic API depending on what is available. Transcription runs on Whisper. Data is stored using SQLAlchemy, starting with SQLite for local development and moving to Postgres for anything beyond that. The frontend, which will come later, is planned in Next.js and deployed on Vercel. The backend itself is containerized with Docker so it can be deployed anywhere.

## Project status

This is an active work in progress. The project structure and scaffolding are in place. Agents and API endpoints are being built out milestone by milestone, starting with transcription and working outward from there.

## Project structure

The backend lives in its own folder with a clear separation between agents, tools, the orchestrator, database models, and API routes. Tests sit alongside the backend code. Docker and docker compose files handle local and future deployment setups. Documentation lives in its own folder and covers architecture, setup, and API details as they get written.

## Getting started

Setup instructions are being finalized and will live in docs/SETUP_GUIDE.md. Once the first milestone is working end to end, this section will be updated with exact steps to run the project locally.

## Roadmap

The rough plan is to get transcription and action item extraction working first, then add the timeline and decision agents, followed by insight generation and automatic follow up emails. Calendar integration and the frontend dashboard come after the backend is solid.

## License

To be added.
