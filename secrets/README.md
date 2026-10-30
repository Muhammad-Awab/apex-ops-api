# secrets/

Git-ignored. Holds local-only secret files, mounted into containers as Docker secrets at `/run/secrets/<name>`.

| File | Created by | Used by |
|------|------------|---------|
| `db_password.txt` | `scripts/init_secrets.sh` (random 32 chars) | `db` (`POSTGRES_PASSWORD_FILE`), `app` (`DB_PASSWORD_FILE`) |

Do not commit real values. In the cloud, these files are replaced by a managed secret store (see `docs/SECURITY.md`).
