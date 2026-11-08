# Meeting Intelligence Engine

![Backend tests](https://github.com/Jai-Negi/meeting-intelligence/actions/workflows/backend-tests.yml/badge.svg)

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

## API

The backend exposes the endpoints below. When the server is running you can also try them in the browser at http://localhost:8000/docs.

`GET /health` returns a simple status so you can check the server is up.

`POST /meetings/upload` accepts a recording as multipart form data in a field called file. Allowed types are mp3, m4a, wav, mp4, webm, ogg, flac and aac, up to the size set by MAX_UPLOAD_SIZE_MB (500 by default). It returns a job id straight away while transcription and analysis carry on in the background. A file that is the wrong type, empty or too large is rejected with a 400 and a plain explanation.

`GET /meetings/{job_id}` returns the status of a job, which is processing, completed or failed. Once the transcript is ready it includes the text, language and timestamped segments, and once analysis finishes it also includes action items, timeline events and decisions. A failed job includes the reason.

`GET /meetings` lists past meetings, newest first, without their full results. It takes an optional limit between 1 and 200, and defaults to 50.

`DELETE /meetings/{job_id}` removes a meeting along with its transcript, extracted results and uploaded audio. It returns a 404 for an unknown job and a 409 while the meeting is still processing.

`POST /meetings/{job_id}/retry` runs the pipeline again for a failed meeting, using the audio saved at upload, and returns a 202 while the work carries on in the background. It returns a 409 if the meeting has not failed or if the audio file is no longer on the server, and a 404 for an unknown job.

If the server restarts while a job is processing, that job can never finish, so on the next startup it is marked as failed with an explanation.

## Running the tests

From the backend folder, install the development requirements and run pytest:

    pip install -r requirements-dev.txt
    python -m pytest tests/ -v

The tests use a throwaway database and uploads folder, so they never touch your real data. The transcription and analysis agents are replaced with fakes, which means the tests need no API keys, no Whisper model and finish in about a second.

## Roadmap

The rough plan is to get transcription and action item extraction working first, then add the timeline and decision agents, followed by insight generation and automatic follow up emails. Calendar integration and the frontend dashboard come after the backend is solid.

## License

To be added.
