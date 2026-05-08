# nexus-worker

Dramatiq workers. Stub package — full scaffold lands in block D when MCP servers + cron jobs come online.

Responsibilities (post-block-D):
- Consume Redis Stream of inbound messages.
- Execute LangGraph agent runs.
- Schedule and dispatch reminders / no-show follow-ups.
- Run AgendaPro health-check cron and `scrape_no_shows` daily cron.
