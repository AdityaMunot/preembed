# Account Recovery

Administrators can rotate recovery tokens after confirming the requester's identity.
Every rotation is written to the audit log together with the approval ticket number.

## Verifying the requester

Ask the requester for the ticket number and confirm it matches an open request in the
support queue. If the request was opened more than seven days ago, ask the requester to
open a new ticket so that the approval trail stays current.

## Rotating the token

```bash
admin-cli tokens rotate --user alice --ticket SUP-4821
```

The command prints the new token once. Share it through the secure messaging channel and
never by email. Tokens expire after twenty-four hours if they are not used.

## Escalation

If identity cannot be confirmed, escalate to the security team on call. Do not rotate the
token until security has approved the request in writing.
