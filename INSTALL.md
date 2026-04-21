# Installing Family Chores

## Option A — custom add-on repository (recommended)

1. In HA, go to **Settings → Add-ons → Add-on Store**.
2. Menu (⋮) → **Repositories** → paste the repo URL and click **Add**.
3. Refresh the store, find **Family Chores**, click **Install**.
4. When it finishes installing, click **Start**. Give it 10–20 seconds to come up.
5. Open the sidebar panel **Family Chores**, or click **Open Web UI** from the
   add-on page.

## Option B — local add-ons folder

Useful when you're iterating on the add-on itself from the HA host.

1. Mount the HA host's `/addons` directory via Samba, SSH, or the
   SSH & Web Terminal add-on.
2. Copy this repository into `/addons/family_chores/` so that
   `/addons/family_chores/config.yaml` exists.
3. In HA, **Settings → Add-ons → Add-on Store → menu (⋮) → Check for updates**.
   "Local add-ons" now includes Family Chores.
4. Click **Install**, then **Start**.

## Configuration

In the add-on's **Configuration** tab:

| Option | Default | Notes |
|---|---|---|
| `log_level` | `info` | Bump to `debug` when filing a bug report. |
| `week_starts_on` | `monday` | Affects the weekly points reset boundary. |
| `sound_default` | `false` | Completion chime default for new browser sessions. |

Changes to any option **restart** the add-on.

## Local development (no HA required)

You can run the backend + frontend on your laptop without a real HA instance.
A small Supervisor stub lets the add-on boot as if HA were there.

```
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
python -m family_chores               # boots on http://localhost:8099

# Frontend (separate terminal, once milestone 6 lands)
cd frontend
npm ci
npm run dev                            # Vite dev server on http://localhost:5173,
                                       # proxies /api to the backend
```

For the full end-to-end dev loop, see `scripts/dev_backend.sh` and
`scripts/dev_frontend.sh` (added in later milestones). A
`docker-compose.yml` is also provided for running the backend + frontend
together in containers without HA.

## Updating

1. HA → **Settings → Add-ons → Family Chores → Update**.
2. Before each Alembic migration, the add-on copies `/data/family_chores.db`
   to `/data/family_chores.db.bak`. If a migration fails, restore that file
   manually from the HA host (`/usr/share/hassio/addons/data/<addon-slug>/`)
   and open an issue.

## Uninstalling

HA preserves `/data` through an uninstall by default — your chore history and
points will survive a reinstall. To wipe the slate, uninstall the add-on and
then delete `/usr/share/hassio/addons/data/<addon-slug>/` from the host
before reinstalling.
