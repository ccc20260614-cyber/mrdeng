# MrDeng

Device management panel for remote device monitoring, task distribution, and license control. Deploy on your own server in 3 minutes.

## Features

- **Device Management** — Register, monitor, and unbind remote devices with heartbeat tracking
- **License System** — Generate tiered license keys (Basic/Studio/Pro/Ultimate) with device limits and expiry
- **Task Distribution** — Create and dispatch tasks to devices with status tracking
- **Data Collection Tools** — Built-in web scraping, Markdown conversion, and auto-scraping utilities
- **Mobile First** — Responsive dark theme UI, works on phone and desktop
- **One-line Install** — Single curl command, zero manual configuration

## Quick Install

SSH into your server and run:

```bash
curl -fsSL https://mrdeng.site/dl/install.sh | sudo bash
```

Requirements: CentOS 7+ / Debian 10+ / Ubuntu 20.04+, Python 3.8+

After installation, open `http://your-server-ip` and login with password `admin123`.

## Tech Stack

- Backend: Python Flask + SQLite + Gunicorn
- Frontend: Vanilla JS + Tailwind CSS (dark theme)
- Deployment: systemd + Nginx reverse proxy

## License

MIT
