# Deploy this API to Railway

This guide deploys the Django API service while keeping the existing MySQL
database and its tables. It does not require Django migrations. Railway hosting,
public access, and database connectivity are not configured from this repository;
those steps happen in your Railway account and with the MySQL host administrator.

## Before creating a Railway deployment

1. Make a verified backup of the existing MySQL database and confirm it can be
   restored. Do not use a Railway template that creates a replacement database.
2. Confirm the existing MySQL server is reachable from Railway over a secure
   connection. A MySQL server at `localhost` on your own computer is not
   reachable by a Railway app. Keep its database name and tables; configure the
   MySQL host/network firewall to accept connections only from an approved
   source. Do not expose MySQL broadly to the public internet.
3. Create a dedicated MySQL application account with only the SELECT, INSERT,
   UPDATE, and DELETE permissions needed on `court_case_system.*`. Do not use
   the MySQL `root` account. This adds a database account/grant, not a table or
   schema change. Have your database administrator do this if you lack the
   required MySQL privileges.
4. Rotate the old MySQL password if it has ever been committed to Git. Keep the
   new value private and enter it directly into Railway Variables.
5. Commit and push the reviewed backend code to the GitHub repository that
   Railway will deploy. Do not commit `.env`.

## Create the Railway web service

1. In Railway, create a project and deploy the existing GitHub repository as a
   service. Do not add a database service or use a template that switches the
   app to a new database.
2. Use the repository root as the service root directory.
3. In the service's **Settings → Build**, set the build command to:

   ```sh
   python manage.py collectstatic --noinput
   ```

   Railway installs packages listed in `requirements.txt` during its normal
   build. This command only prepares static files.

4. In **Settings → Deploy**, set the start command to:

   ```sh
   gunicorn court_system.wsgi:application --bind 0.0.0.0:$PORT
   ```

   This uses a production WSGI server and Railway's assigned port. Do not use
   `python manage.py runserver` for the deployed service.

   **Set this custom start command before the first deployment.** Railway's
   automatic Django start command may include `python manage.py migrate`. This
   project must not run that command because its court tables belong to the
   existing unmanaged database.
5. Add the environment variables below in the service's **Variables** tab. Set
   secret values directly in Railway; do not paste them into source files,
   tickets, or chat.

| Variable | Value |
| --- | --- |
| `DJANGO_SECRET_KEY` | A newly generated, private Django key. Generate locally with `venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`, then paste it into Railway. |
| `DJANGO_DEBUG` | `false` |
| `DJANGO_ALLOWED_HOSTS` | Railway's generated API hostname only, without `https://` (for example, `my-api.up.railway.app`). Add a custom API domain here too if you use one. |
| `CORS_ALLOWED_ORIGINS` | Exact frontend origin(s), including `https://` and no path. Do not use `*`. |
| `DB_NAME` | `court_case_system` |
| `DB_USER` | The dedicated application MySQL account |
| `DB_PASSWORD` | That account's newly rotated password |
| `DB_HOST` | The network hostname of the existing MySQL server; not `localhost` unless MySQL is running in the same container (it should not be for this setup). |
| `DB_PORT` | The existing MySQL server port, usually `3306` |

6. In **Settings → Networking**, generate a Railway domain for the API. Put
   that hostname into `DJANGO_ALLOWED_HOSTS`, save the variable, and redeploy.
   Railway provides HTTPS for its public domains. This project recognizes
   Railway's `X-Forwarded-Proto` header when `DJANGO_DEBUG=false` so Django's
   HTTPS redirect works behind Railway's TLS edge.
7. If Railway offers a health-check path, set it to `/api/`. The API root is a
   public GET endpoint; protected data endpoints still require a Bearer token.

## Database safety rules for deployment

- Never run `python manage.py migrate` or `makemigrations` for this app's
  existing court tables.
- Never leave Railway's automatically detected Django start command in place if
  it includes migrations; replace it with the Gunicorn command above.
- The Railway build command above only installs Python packages and collects
  static files; it does not modify database tables.
- Before turning on writes in the deployed app, verify the configured DB host,
  database name, and backup. The app's regular API endpoints can insert, update,
  and delete court data based on the caller's role.
- Railway does not automatically provide a private connection to a MySQL
  server hosted elsewhere. Confirm the DB host firewall and encrypted MySQL
  connection requirements with the host. Do not solve connectivity by allowing
  every IP to access MySQL.

## Check before and after the first deployment

Run these locally before pushing (use your active virtual environment):

```powershell
venv\Scripts\python.exe manage.py check
venv\Scripts\python.exe manage.py check --deploy
venv\Scripts\python.exe manage.py shell -c "from cases.tests import run_isolated_tests; raise SystemExit(run_isolated_tests())"
```

`check --deploy` may report deployment warnings; review each one against the
actual hosting/domain configuration. Do not silence a warning just to make the
command green. The isolated test command does not create a test database.

After deploying, use the Railway logs and your browser/API client to verify:

1. `GET https://<api-host>/api/` returns the API links.
2. `POST https://<api-host>/api/auth/login/` succeeds with a real test account;
   do not put a real password in a URL or logs.
3. Use the returned Bearer token to check cases, hearings, filtering, and the
   role restrictions; verify anonymous requests to protected endpoints return
   `401` and forbidden actions return `403`.
4. Verify the API is reading the intended existing MySQL database and the known
   records are present. If testing writes, use clearly identified test records
   and remove them through the API after confirming the behavior.
5. Confirm a browser frontend can call the API from its exact configured CORS
   origin.
6. Confirm invalid hostnames are rejected, HTTPS redirects correctly, and
   secrets do not appear in repository files or Railway logs.

## Operating the deployed API

- Keep database backups and test restores periodically.
- Keep Railway variables private; rotate Django and database credentials if
  they are exposed. Rotating `DJANGO_SECRET_KEY` invalidates all currently
  issued eight-hour API tokens, so schedule that rotation accordingly.
- Review Railway application logs after deployments and remove unnecessary
  secrets or request data from logging.
- Do not consider the project deployed until a real production URL passes the
  checks above and the existing database owner confirms backups and access.

## References

- [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [Railway Django deployment guide](https://docs.railway.com/guides/django)
- [Railway environment variables](https://docs.railway.com/variables)
- [Railway public domains and HTTPS](https://docs.railway.com/networking/domains/working-with-domains)
