# Media Embedder Bot

A small Telegram bot that watches messages for supported media URLs and replies
with URLs from services that provide better inline previews. Each matching URL
gets its own reply so Telegram can render a preview for every link.

The service mappings are defined in
[`media_services.json`](media_services.json). The first target for each service
is used.

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy its token.
2. In BotFather, open **Bot Settings > Group Privacy** and turn privacy mode off.
3. Remove and re-add the bot to existing groups after changing privacy mode.
4. Give the bot permission to post messages in each group or channel.
5. Start the bot:

```sh
export TELEGRAM_BOT_TOKEN="your-token"
python3 bot.py
```

Python 3.11 or newer is required. There are no third-party dependencies.

## Docker

```sh
docker build -t media-embedder-bot .
docker run --rm -e TELEGRAM_BOT_TOKEN="your-token" media-embedder-bot
```

For a persistent deployment, create `.env` from `.env.example` and run:

```sh
docker compose up -d --build
docker compose logs -f bot
```

Docker rotates the bot logs after 10 MB and retains three files, limiting
stored container logs to approximately 30 MB.

Only one running instance may poll a given bot token. Remove any configured
webhook before using this long-polling bot.

## CircleCI Deployment

The pipeline in `.circleci/config.yml` tests every branch and deploys `master`
to a server over SSH after tests pass. CircleCI uploads only the application
files; the Telegram token stays in the server-side `.env`.

### Prepare the Hetzner server

Install Docker Engine, then verify that the deployment user can access it:

```sh
docker version
```

Then create the deployment user and application directory:

```sh
sudo useradd --create-home --shell /bin/bash deploy
sudo usermod --append --groups docker deploy
sudo mkdir -p /opt/media-embedder-bot
sudo chown deploy:deploy /opt/media-embedder-bot
sudo -u deploy sh -c 'umask 077; printf "%s\n" \
  "TELEGRAM_BOT_TOKEN=replace-with-your-token" \
  > /opt/media-embedder-bot/.env'
```

Log out and back in after adding `deploy` to the `docker` group. Verify that
`docker version` works as that user. The CircleCI deployment uses Docker
directly and does not require Docker Compose, allowing it to run on legacy
hosts where the Compose V2 package is unavailable.

### Keep Docker running

Docker already supervises the bot through its `unless-stopped` restart policy.
Configure systemd to restart the Docker daemon if it crashes:

```sh
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo cp ops/docker-restart.conf \
  /etc/systemd/system/docker.service.d/restart.conf
sudo systemctl daemon-reload
sudo systemctl enable docker.service
sudo systemctl restart docker.service
```

For additional protection, enable Docker live-restore so running containers
remain active while the Docker daemon is unavailable. If `/etc/docker/daemon.json`
does not exist, create it with:

```json
{
  "live-restore": true
}
```

If that file already exists, add `"live-restore": true` to the existing JSON
object instead of replacing it. Validate and apply the configuration:

```sh
sudo dockerd --validate --config-file=/etc/docker/daemon.json
sudo systemctl restart docker.service
sudo systemctl is-enabled docker.service
sudo systemctl is-active docker.service
```

The `dockerd --validate` option may be unavailable on older Docker releases. In
that case, validate the JSON with `python -m json.tool /etc/docker/daemon.json`
before restarting Docker. An application-specific systemd unit is intentionally
not used because systemd and Docker should not both manage the same container.

### Configure SSH

Generate a dedicated key locally with no passphrase:

```sh
ssh-keygen -t ed25519 -N "" -f circleci_hetzner -C circleci-media-embedder
ssh-copy-id -i circleci_hetzner.pub deploy@YOUR_SERVER_IP
```

In CircleCI, open **Project Settings > SSH Keys > Additional SSH Keys**. Add
`YOUR_SERVER_IP` as the hostname and paste the contents of the private
`circleci_hetzner` key. Do not commit either key.

Read the server's SSH host public key from the Hetzner console or an existing
trusted SSH session:

```sh
printf '%s ' "YOUR_SERVER_IP"
sudo cat /etc/ssh/ssh_host_ed25519_key.pub
```

### Configure CircleCI

In **Project Settings > Environment Variables**, add:

| Variable | Example |
| --- | --- |
| `DEPLOY_HOST` | `203.0.113.10` |
| `DEPLOY_USER` | `deploy` |
| `DEPLOY_PATH` | `/opt/media-embedder-bot` |
| `DEPLOY_KNOWN_HOSTS` | `203.0.113.10 ssh-ed25519 AAAA...` |

Add the repository as a CircleCI project and push to `master`. The deploy job
builds the image on the Hetzner server, requires the new container to run for
60 seconds without restarting, and restores the previous image if that check
fails. Use `docker logs -f media-embedder-bot` on the server to inspect it. The
previous image remains tagged as `media-embedder-bot:rollback` for manual
recovery.

## Supported Links

Twitter/X, TikTok, Reddit, and Instagram links are currently
supported. YouTube links are intentionally left unchanged because Telegram
does not render the available third-party embed frontends as native video.
Edit `media_services.json` to add a service or change target priority.
Instagram links prefer `kkinstagram.com`, and Reddit links prefer
`vxreddit.com`.

The bot recognizes `http://`, `https://`, and `www.` URLs in normal message text
and media captions. It ignores messages sent by bots to avoid reply loops.

## Tests

```sh
python3 -m unittest discover -v
```
