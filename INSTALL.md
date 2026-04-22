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
| `timezone` | `""` | Optional IANA name. Empty = follow HA (fetched from `/api/config`). |

Changes to any option **restart** the add-on.

## HA To-do Setup (required for calendar + todo sync)

Home Assistant surfaces due-dated todo items on the calendar automatically,
and that's where Family Chores' calendar view comes from. Because add-ons
can't create entities themselves, you create one **Local To-do** list per
family member; Family Chores fills it in.

### Steps

1. **Settings → Devices & Services → Add Integration → "Local To-do"**.
2. Give it a recognisable name — e.g. `Alice Chores`.
3. Repeat for each family member.
4. After creating, open **Developer Tools → States** and filter for `todo.`.
   Copy the entity ID for each list (`todo.alice_chores`, etc.).
5. In **Family Chores → parent mode → member detail**, paste that entity ID
   into the "HA to-do entity" field for the matching member.

Once saved, Family Chores will:

- Add a todo item for each of the member's upcoming chore instances.
- Flip items to **completed** when the kid marks the chore done (and again,
  if needed, after parent approval).
- Remove orphan items on startup and every 15 minutes (a safety reconcile).

Items Family Chores manages start with `[FC#<id>]`; manually-added items
outside that prefix are left alone.

### If you skip this

Sensors (`sensor.family_chores_<slug>_points`, `_streak`, and the global
`pending_approvals` counter) still publish. Events still fire. You just
lose the calendar / todo-list view in HA; the add-on's own UI is unaffected.

### Permissions

The add-on talks to HA via the Supervisor proxy using the automatically
provisioned `SUPERVISOR_TOKEN`. No manual token setup. If you see 401s in
the add-on log, check that the manifest still grants `hassio_api: true`,
`hassio_role: default`, and `homeassistant_api: true`.

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
