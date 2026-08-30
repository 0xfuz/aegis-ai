# Secure Production Administrator Bootstrap (R1)

R1 provides an internal operator command for creating the first administrator.
It is not an HTTP endpoint and must be run only after migration `0024` is at
the Alembic head. It creates exactly one organization-scoped administrator and
requires a password rotation before privileged access.

## Preconditions

- `ENVIRONMENT=production`, `DEBUG=false`, and `SEED_DEMO_DATA=false`.
- Baseline database migration completed through `0024`.
- The administrator email, organization name, and organization slug are
  operator-supplied. Demo identity `admin@aegis.demo` is rejected.
- Supply a password that is 12–128 characters and uses at least three of:
  lowercase, uppercase, digits, and symbols. Default/demo passwords are
  rejected.

Do not use demo seeding to create a production administrator.

## Run the internal command

Prefer a Docker/Kubernetes secret mounted as a regular file. The password is
never accepted as an argument:

```bash
python -m app.modules.identity.cli.bootstrap_admin \
  --organization-name "Example Security" \
  --organization-slug example-security \
  --email "admin@example.com" \
  --full-name "Initial Administrator" \
  --password-file /run/secrets/aegis_initial_admin_password
```

For a controlled interactive terminal, omit `--password-file`; the command
uses a non-echoing password prompt. Do not redirect the prompt, place a
password in shell history, pass a `--password` option, or store it in an
environment variable.

The command writes only the password hash. Its audit event records the
operator bootstrap action and that rotation is required; it never contains the
plaintext credential.

Repeated or concurrent invocation for the same organization slug fails closed;
the organization and administrator are created atomically with no duplicate
scope.

## Required initial rotation

The first login response has `password_rotation_required: true`. Its access
token may inspect identity state, refresh, log out, and call the authenticated
rotation endpoint, but privileged role/permission dependencies reject it until
rotation completes.

Over HTTPS, rotate with the current bootstrap password and a new compliant
password:

```text
POST /api/v1/auth/password/rotate
Authorization: Bearer <initial-access-token>
{"current_password":"…","new_password":"…"}
```

Sign in again using the new password. The original password must fail. The
rotation is recorded as a safe `CREDENTIAL_ROTATED` audit event without either
password. Destroy or revoke access to the initial Docker secret after this
verification.

Existing users are not reinterpreted: migration `0024` defaults
`must_rotate_password` to `false`. This command is not a general user-creation
or password-reset interface.
# Operator password recovery

Recovery is internal-only and has no HTTP endpoint:

```bash
python -m app.modules.identity.cli.reset_admin_password \
  --organization-slug YOUR_ORGANIZATION --email ADMIN_EMAIL \
  --password-file /protected/recovery/new-password
```

Without `--password-file`, the command requests and confirms a non-echoing password. It runs only with `ENVIRONMENT=production`, `DEBUG=false`, and demo seeding disabled; password arguments and password environment variables are intentionally unsupported. The target must be exactly one active administrator in the named organization. Recovery sets `must_rotate_password=true` and records only safe operator audit metadata. Rotate the JWT signing secret through the supported credential-rotation procedure before or with recovery to invalidate existing sessions.
