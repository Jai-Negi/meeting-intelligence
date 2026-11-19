# Meeting Intelligence Engine

![Backend tests](https://github.com/Jai-Negi/meeting-intelligence/actions/workflows/backend-tests.yml/badge.svg)
![Frontend checks](https://github.com/Jai-Negi/meeting-intelligence/actions/workflows/frontend-checks.yml/badge.svg)

A multi agent system that takes a recorded meeting and turns it into something actually useful: a clean transcript, a list of action items, key decisions, a timeline, and a follow up email draft. The goal is to save people from re watching an hour long call just to remember what was agreed on.

## What it does

You upload a meeting recording. The system transcribes it using Whisper, then runs a set of agents on top of that transcript to pull out structured information. Right now that includes:

- Transcription with timestamped segments
- Action items, so you know who is doing what
- A timeline of what was discussed and when
- Key decisions that were made during the call
- A follow up email draft you can edit and copy

Each of these is handled by its own agent, built on a shared base class that takes care of retries, timeouts, and basic guardrails so one failing agent does not take down the whole pipeline.

## Why I built this

I wanted a project that goes beyond a simple wrapper around an LLM call. This one deals with real production concerns: async job handling, structured logging, error recovery, and a system design that can scale past a single script. It is also something I actually plan to use myself once the core features are working.

## Tech stack

Backend is built with FastAPI and Python. Each agent is a small class on a shared base that handles retries and timeouts, and the three extraction agents run concurrently with asyncio. The LLM layer can run through Groq, locally through Ollama, or against the Anthropic API depending on what is available. Transcription runs on Whisper, either locally or through Groq. Data is stored using SQLAlchemy, starting with SQLite for local development and moving to Postgres for anything beyond that. The frontend is Next.js. The backend is containerized with Docker so it can be deployed anywhere.

## Project status

This is an active work in progress. Transcription, action items, timeline, decisions, history, retry, and follow-up email drafts are in place, along with a Next.js UI for uploading recordings and reviewing past meetings.

## Project structure

The backend lives in its own folder with a clear separation between agents, tools, database models, schemas, and API routes. Tests sit alongside the backend code. The frontend lives in its own folder. The docker folder holds a compose file for running the backend locally.

## Getting started

In the backend folder, copy `.env.example` to `.env` and fill in the keys you use. Then create a virtual environment, install the requirements and start the API:

    cd backend
    python3.11 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    python -m uvicorn app.main:app --reload

Local transcription needs ffmpeg, which you can install on macOS with `brew install ffmpeg`. If you would rather not run Whisper on your own machine, set TRANSCRIPTION_PROVIDER to groq and install `requirements-base.txt` instead, which leaves out Whisper and torch.

In another terminal, from the frontend folder, run `npm install` and `npm run dev`, then open http://localhost:3000. The API docs are at http://localhost:8000/docs.

## API

The backend exposes the endpoints below. When the server is running you can also try them in the browser at http://localhost:8000/docs.

`GET /health` returns a simple status so you can check the server is up.

`POST /meetings/upload` accepts a recording as multipart form data in a field called file. Allowed types are mp3, m4a, wav, mp4, webm, ogg, flac and aac, up to the size set by MAX_UPLOAD_SIZE_MB (500 by default). When transcription runs through Groq, aac is refused and the limit is capped at 25 MB, because that is what Groq's free tier accepts. It returns a job id straight away while transcription and analysis carry on in the background. A file that is the wrong type, empty or too large is rejected with a 400 and a plain explanation.

`GET /meetings/{job_id}` returns the status of a job, which is processing, completed or failed. Once the transcript is ready it includes the text, language and timestamped segments, and once analysis finishes it also includes action items, timeline events and decisions. A failed job includes the reason.

`GET /meetings` lists past meetings, newest first, without their full results. It takes an optional limit between 1 and 200, and defaults to 50.

`DELETE /meetings/{job_id}` removes a meeting along with its transcript, extracted results and uploaded audio. It returns a 404 for an unknown job and a 409 while the meeting is still processing.

`POST /meetings/{job_id}/retry` runs the pipeline again for a failed meeting, using the audio saved at upload, and returns a 202 while the work carries on in the background. It returns a 409 if the meeting has not failed or if the audio file is no longer on the server, and a 404 for an unknown job.

`POST /meetings/{job_id}/email` drafts a follow up email for a finished meeting from its transcript, action items and decisions, and returns a subject and a body. Nothing is stored, so asking again simply gives a fresh draft. It returns a 409 until the meeting has finished processing, a 404 for an unknown job, and a 502 with the reason if the language model could not produce a usable draft.

If the server restarts while a job is processing, that job can never finish, so on the next startup it is marked as failed with an explanation.

## Running the tests

From the backend folder, install the development requirements and run pytest:

    pip install -r requirements-dev.txt
    python -m pytest tests/ -v

The tests use a throwaway database and uploads folder, so they never touch your real data. The transcription and analysis agents are replaced with fakes, which means the tests need no API keys, no Whisper model and finish in about a second. CI runs the suite twice, once with the full requirements and once with only the base requirements, to prove the slim install works without Whisper.

## Docker

`backend/Dockerfile` builds the full image with local Whisper, and `docker/docker-compose.yml` runs it with the database and uploads kept on your machine. `backend/Dockerfile.hosted` builds a much smaller image without Whisper or torch that transcribes through Groq and listens on the port given in the PORT environment variable, which suits most hosting platforms.

## Roadmap

The remaining work is meeting summaries, calendar integration, and tightening the dashboard. Transcription, extraction, follow-up emails, and the frontend are already in the repo.

## License

MIT. See `LICENSE`.
